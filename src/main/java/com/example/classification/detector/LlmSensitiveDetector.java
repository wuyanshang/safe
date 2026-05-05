package com.example.classification.detector;

import com.example.classification.config.ClassificationProperties;
import com.example.classification.model.ClassificationResult;
import com.example.classification.model.SensitiveResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import java.nio.charset.StandardCharsets;

@Slf4j
@Component
public class LlmSensitiveDetector {

    private final OpenAiChatModel chatModel;
    private final ClassificationProperties properties;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private String promptTemplate;

    public LlmSensitiveDetector(OpenAiChatModel chatModel,
                                ClassificationProperties properties) {
        this.chatModel = chatModel;
        this.properties = properties;
    }

    @PostConstruct
    public void init() {
        try {
            ClassPathResource resource = new ClassPathResource("prompts/sensitive-detection.txt");
            promptTemplate = new String(resource.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            log.info("敏感检测 prompt 模板加载成功");
        } catch (Exception e) {
            throw new RuntimeException("加载敏感检测 prompt 模板失败", e);
        }
    }

    /**
     * 对单个字段进行 LLM 敏感分类检测
     */
    public void detect(ClassificationResult result) {
        String prompt = buildPrompt(result);
        int maxRetries = properties.getMaxRetries();

        for (int attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                String response = ChatClient.create(chatModel)
                        .prompt()
                        .user(prompt)
                        .call()
                        .content();

                SensitiveResponse sensitiveResponse = parseResponse(response);
                result.applyResponse(sensitiveResponse);
                return;
            } catch (Exception e) {
                log.warn("敏感检测 LLM 调用失败 (第 {}/{} 次), 字段: {}.{}, 错误: {}",
                        attempt, maxRetries, result.getTableEn(), result.getFieldEn(), e.getMessage());
                if (attempt == maxRetries) {
                    result.markFailed("LLM调用失败，需人工确认: " + e.getMessage());
                }
            }
        }
    }

    private String buildPrompt(ClassificationResult result) {
        return promptTemplate
                .replace("{system_cn}", safeStr(result.getSystemCn()))
                .replace("{table_cn}", safeStr(result.getTableCn()))
                .replace("{table_en}", safeStr(result.getTableEn()))
                .replace("{field_cn}", safeStr(result.getFieldCn()))
                .replace("{field_en}", safeStr(result.getFieldEn()));
    }

    private SensitiveResponse parseResponse(String response) throws Exception {
        String json = extractJson(response);
        return objectMapper.readValue(json, SensitiveResponse.class);
    }

    private String extractJson(String response) {
        if (response == null) {
            throw new RuntimeException("LLM 返回为空");
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
        throw new RuntimeException("无法从 LLM 响应中提取 JSON: " + trimmed);
    }

    private String safeStr(String s) {
        return s == null ? "" : s;
    }
}
