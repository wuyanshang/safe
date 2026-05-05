package com.example.classification.workflow;

import com.alibaba.cloud.ai.graph.CompiledGraph;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.example.classification.model.ClassificationResult;
import com.example.classification.model.FieldInput;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Collections;
import java.util.stream.Collectors;

@Slf4j
@Component
public class ClassificationWorkflow {

    private final CompiledGraph classificationGraph;

    public ClassificationWorkflow(CompiledGraph classificationGraph) {
        this.classificationGraph = classificationGraph;
    }

    @SuppressWarnings("unchecked")
    public List<ClassificationResult> execute(List<FieldInput> inputs) {
        String batchNo = generateBatchNo();
        log.info("========== 开始分类分级, 批次号: {}, 字段总数: {} ==========", batchNo, inputs.size());

        // 构建初始结果列表
        List<ClassificationResult> results = inputs.stream()
                .map(input -> ClassificationResult.from(input, batchNo))
                .collect(Collectors.toList());

        // 构建初始状态
        Map<String, Object> initialState = new HashMap<>();
        initialState.put("results", results);
        initialState.put("batchNo", batchNo);

        // 执行工作流图
        try {
            Optional finalState = classificationGraph.invoke(initialState);
            if (finalState.isPresent()) {
                OverAllState state = (OverAllState) finalState.get();
                return (List<ClassificationResult>) state.value("results").orElse(results);
            }
        } catch (Exception e) {
            log.error("工作流执行失败: {}", e.getMessage(), e);
            throw new RuntimeException("工作流执行失败", e);
        }

        return results;
    }

    private String generateBatchNo() {
        return LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
    }
}
