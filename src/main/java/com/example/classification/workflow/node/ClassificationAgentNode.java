package com.example.classification.workflow.node;

import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import com.example.classification.config.ClassificationProperties;
import com.example.classification.knowledge.KnowledgeBaseSearchTool;
import com.example.classification.model.ClassificationResponse;
import com.example.classification.model.ClassificationResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

/**
 * Agent 分类分级节点：使用 ES 知识库 3 个检索工具 + Tool Calling 自动迭代
 * Agent 自主决定搜什么、搜几次，最终判断字段的敏感分类和安全级别
 */
@Slf4j
@Component
public class ClassificationAgentNode implements NodeAction {

    private final OpenAiChatModel chatModel;
    private final KnowledgeBaseSearchTool kbSearchTool;
    private final ClassificationProperties properties;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final ExecutorService executor;
    private String promptTemplate;

    public ClassificationAgentNode(OpenAiChatModel chatModel,
                                   KnowledgeBaseSearchTool kbSearchTool,
                                   ClassificationProperties properties) {
        this.chatModel = chatModel;
        this.kbSearchTool = kbSearchTool;
        this.properties = properties;
        this.executor = Executors.newFixedThreadPool(properties.getThreadCount());
    }

    @PostConstruct
    public void init() {
        try {
            ClassPathResource resource = new ClassPathResource("prompts/classification-agent.txt");
            promptTemplate = new String(resource.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            log.info("分类分级 Agent prompt 加载成功");
        } catch (Exception e) {
            throw new RuntimeException("加载分类分级 Agent prompt 失败", e);
        }
    }

    @Override
    @SuppressWarnings("unchecked")
    public Map<String, Object> apply(OverAllState state) {
        List<ClassificationResult> results =
                (List<ClassificationResult>) state.value("results").orElseThrow();

        // 过滤待处理字段（PENDING 状态）
        List<ClassificationResult> candidates = results.stream()
                .filter(r -> "PENDING".equals(r.getStatus()))
                .collect(Collectors.toList());

        log.info("Agent 分类分级: 待处理 {} 条, 线程数 {}", candidates.size(), properties.getThreadCount());

        if (candidates.isEmpty()) {
            return Map.of("results", results);
        }

        // 按表分组：同表字段串行（共享上下文），不同表并行
        Map<String, List<ClassificationResult>> byTable = candidates.stream()
                .collect(Collectors.groupingBy(
                        r -> safeStr(r.getSystemCn()) + "|" + safeStr(r.getTableEn()),
                        LinkedHashMap::new,
                        Collectors.toList()
                ));

        AtomicInteger processed = new AtomicInteger(0);
        CountDownLatch latch = new CountDownLatch(candidates.size());

        for (Map.Entry<String, List<ClassificationResult>> entry : byTable.entrySet()) {
            executor.submit(() -> {
                StringBuilder tableContext = new StringBuilder();
                for (ClassificationResult field : entry.getValue()) {
                    try {
                        classifySingle(field, tableContext.toString());
                        tableContext.append(String.format("%s→%s; ",
                                safeStr(field.getFieldCn()),
                                field.isSuspectedSensitive() ? "敏感" : "非敏感"));
                    } catch (Exception e) {
                        log.error("Agent 分类异常: {}.{} - {}",
                                field.getTableEn(), field.getFieldEn(), e.getMessage());
                        field.markFailed("Agent调用失败: " + e.getMessage());
                    } finally {
                        int count = processed.incrementAndGet();
                        if (count % 50 == 0 || count == candidates.size()) {
                            log.info("  Agent 分类已处理 {}/{}", count, candidates.size());
                        }
                        latch.countDown();
                    }
                }
            });
        }

        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.error("Agent 分类并发处理被中断", e);
        }

        long sensitive = candidates.stream().filter(ClassificationResult::isSuspectedSensitive).count();
        long failed = candidates.stream().filter(r -> "FAILED".equals(r.getStatus())).count();
        log.info("  Agent 分类完成: 疑似敏感 {} 条, 非敏感 {} 条, 失败 {} 条",
                sensitive, candidates.size() - sensitive - failed, failed);

        return Map.of("results", results);
    }

    /**
     * 对单个字段执行 Agent 分类（ChatClient 内部自动处理多轮 Tool Calling）
     */
    private void classifySingle(ClassificationResult field, String tableContext) {
        String prompt = buildPrompt(field, tableContext);
        int maxRetries = properties.getMaxRetries();

        for (int attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                String response = ChatClient.create(chatModel)
                        .prompt()
                        .user(prompt)
                        .tools(kbSearchTool)
                        .call()
                        .content();

                ClassificationResponse resp = parseResponse(response);
                field.setSuspectedSensitive(resp.isSuspectedSensitive());
                field.setReason(resp.getReason());
                field.setStatus("SUCCESS");
                return;
            } catch (Exception e) {
                log.warn("Agent 调用失败 (第 {}/{} 次), 字段: {}.{}, 错误: {}",
                        attempt, maxRetries, field.getTableEn(), field.getFieldEn(), e.getMessage());
                if (attempt == maxRetries) {
                    field.markFailed("Agent调用" + maxRetries + "次均失败，需人工确认");
                }
            }
        }
    }

    private String buildPrompt(ClassificationResult field, String tableContext) {
        String prompt = promptTemplate
                .replace("{system_cn}", safeStr(field.getSystemCn()))
                .replace("{table_cn}", safeStr(field.getTableCn()))
                .replace("{table_en}", safeStr(field.getTableEn()))
                .replace("{field_cn}", safeStr(field.getFieldCn()))
                .replace("{field_en}", safeStr(field.getFieldEn()));

        if (!tableContext.isEmpty()) {
            prompt += "\n\n## 同表已判断字段（供参考）\n" + tableContext;
        }
        return prompt;
    }

    private ClassificationResponse parseResponse(String response) throws Exception {
        String json = extractJson(response);
        return objectMapper.readValue(json, ClassificationResponse.class);
    }

    private String extractJson(String response) {
        if (response == null) {
            throw new RuntimeException("Agent 返回为空");
        }
        String trimmed = response.trim();
        if (trimmed.startsWith("{")) {
            int end = trimmed.lastIndexOf("}");
            if (end >= 0) return trimmed.substring(0, end + 1);
        }
        int jsonStart = trimmed.indexOf("```json");
        if (jsonStart >= 0) {
            int start = trimmed.indexOf("{", jsonStart);
            int end = trimmed.lastIndexOf("}");
            if (start >= 0 && end >= start) return trimmed.substring(start, end + 1);
        }
        int start = trimmed.indexOf("{");
        int end = trimmed.lastIndexOf("}");
        if (start >= 0 && end >= start) return trimmed.substring(start, end + 1);
        throw new RuntimeException("无法从 Agent 响应中提取 JSON: " + trimmed);
    }

    private String safeStr(String s) {
        return s == null ? "" : s;
    }
}
