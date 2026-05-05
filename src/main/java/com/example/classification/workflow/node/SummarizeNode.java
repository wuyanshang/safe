package com.example.classification.workflow.node;

import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import com.example.classification.model.ClassificationResult;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 汇总统计节点
 */
@Slf4j
@Component
public class SummarizeNode implements NodeAction {

    @Override
    @SuppressWarnings("unchecked")
    public Map<String, Object> apply(OverAllState state) {
        List<ClassificationResult> results =
                (List<ClassificationResult>) state.value("results").orElseThrow();

        long total = results.size();
        long sensitiveCount = results.stream().filter(ClassificationResult::isSuspectedSensitive).count();
        long nonSensitiveCount = results.stream()
                .filter(r -> "SUCCESS".equals(r.getStatus()) && !r.isSuspectedSensitive()).count();
        long failedCount = results.stream().filter(r -> "FAILED".equals(r.getStatus())).count();

        // 按目录节点统计
        Map<String, Long> catalogStats = results.stream()
                .filter(r -> r.isSuspectedSensitive() && r.getCatalogNode() != null)
                .collect(Collectors.groupingBy(ClassificationResult::getCatalogNode, Collectors.counting()));

        log.info("========== 分类分级完成 ==========");
        log.info("  总计: {} 条", total);
        log.info("  疑似敏感: {} 条 ({})", sensitiveCount, pct(sensitiveCount, total));
        log.info("  非敏感: {} 条 ({})", nonSensitiveCount, pct(nonSensitiveCount, total));
        if (failedCount > 0) {
            log.info("  失败: {} 条", failedCount);
        }
        if (!catalogStats.isEmpty()) {
            log.info("  按目录节点统计:");
            catalogStats.forEach((node, count) ->
                    log.info("    {}: {} 条", node, count));
        }

        return Map.of("results", results);
    }

    private String pct(long part, long total) {
        if (total == 0) return "0%";
        return String.format("%.1f%%", part * 100.0 / total);
    }
}
