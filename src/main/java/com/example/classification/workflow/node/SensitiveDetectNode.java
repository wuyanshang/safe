package com.example.classification.workflow.node;

import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import com.example.classification.config.ClassificationProperties;
import com.example.classification.detector.LlmSensitiveDetector;
import com.example.classification.model.ClassificationResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * LLM 敏感字段分类检测节点（多线程并发）
 */
@Slf4j
@Component
public class SensitiveDetectNode implements NodeAction {

    private final LlmSensitiveDetector detector;
    private final ExecutorService executor;

    public SensitiveDetectNode(LlmSensitiveDetector detector,
                               ClassificationProperties properties) {
        this.detector = detector;
        this.executor = Executors.newFixedThreadPool(properties.getThreadCount());
        log.info("敏感检测节点初始化, 线程数: {}", properties.getThreadCount());
    }

    @Override
    @SuppressWarnings("unchecked")
    public Map<String, Object> apply(OverAllState state) {
        List<ClassificationResult> results =
                (List<ClassificationResult>) state.value("results").orElseThrow();

        log.info("步骤1: LLM 敏感分类检测, 待处理 {} 条", results.size());

        if (results.isEmpty()) {
            return Map.of("results", results);
        }

        AtomicInteger processed = new AtomicInteger(0);
        CountDownLatch latch = new CountDownLatch(results.size());

        for (ClassificationResult result : results) {
            executor.submit(() -> {
                try {
                    detector.detect(result);
                    int count = processed.incrementAndGet();
                    if (count % 50 == 0 || count == results.size()) {
                        log.info("  敏感检测已处理 {}/{}", count, results.size());
                    }
                } catch (Exception e) {
                    log.error("  敏感检测处理异常: {}.{} - {}",
                            result.getTableEn(), result.getFieldEn(), e.getMessage());
                    result.markFailed("处理异常: " + e.getMessage());
                } finally {
                    latch.countDown();
                }
            });
        }

        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.error("敏感检测并发处理被中断", e);
        }

        long sensitiveCount = results.stream().filter(ClassificationResult::isSuspectedSensitive).count();
        long failedCount = results.stream().filter(r -> "FAILED".equals(r.getStatus())).count();
        log.info("  敏感检测完成: 疑似敏感 {} 条, 非敏感 {} 条, 失败 {} 条",
                sensitiveCount, results.size() - sensitiveCount - failedCount, failedCount);

        return Map.of("results", results);
    }
}
