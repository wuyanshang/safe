package com.example.classification.workflow;

import com.alibaba.cloud.ai.graph.CompiledGraph;
import com.alibaba.cloud.ai.graph.KeyStrategy;
import com.alibaba.cloud.ai.graph.KeyStrategyFactory;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import com.alibaba.cloud.ai.graph.state.strategy.ReplaceStrategy;
import com.example.classification.workflow.node.SensitiveDetectNode;
import com.example.classification.workflow.node.SummarizeNode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.HashMap;
import java.util.Map;

import static com.alibaba.cloud.ai.graph.StateGraph.END;
import static com.alibaba.cloud.ai.graph.StateGraph.START;
import static com.alibaba.cloud.ai.graph.action.AsyncNodeAction.node_async;

@Configuration
public class ClassificationGraphConfig {

    @Bean
    public CompiledGraph classificationGraph(
            SensitiveDetectNode sensitiveDetectNode,
            SummarizeNode summarizeNode) throws GraphStateException {

        KeyStrategyFactory keyStrategyFactory = () -> {
            Map<String, KeyStrategy> keyStrategyMap = new HashMap<>();
            keyStrategyMap.put("results", new ReplaceStrategy());
            keyStrategyMap.put("batchNo", new ReplaceStrategy());
            return keyStrategyMap;
        };

        StateGraph graph = new StateGraph("classification", keyStrategyFactory)
                .addNode("sensitiveDetect", node_async(sensitiveDetectNode))
                .addNode("summarize", node_async(summarizeNode))
                .addEdge(START, "sensitiveDetect")
                .addEdge("sensitiveDetect", "summarize")
                .addEdge("summarize", END);

        return graph.compile();
    }
}
