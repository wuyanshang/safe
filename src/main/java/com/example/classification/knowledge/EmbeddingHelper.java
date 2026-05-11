package com.example.classification.knowledge;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.MetadataMode;
import org.springframework.ai.openai.OpenAiEmbeddingModel;
import org.springframework.ai.openai.OpenAiEmbeddingOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Embedding 工具类，封装向量化调用
 */
@Slf4j
@Component
public class EmbeddingHelper {

    @Value("${knowledge-base.embedding.api-key:}")
    private String apiKey;

    @Value("${knowledge-base.embedding.base-url:https://dashscope.aliyuncs.com/compatible-mode/v1}")
    private String baseUrl;

    @Value("${knowledge-base.embedding.model:text-embedding-v4}")
    private String model;

    private OpenAiEmbeddingModel embeddingModel;

    @PostConstruct
    public void init() {
        if (apiKey == null || apiKey.isBlank()) {
            log.warn("knowledge-base.embedding.api-key 未配置，语义搜索不可用");
            return;
        }

        OpenAiApi openAiApi = OpenAiApi.builder()
                .apiKey(apiKey)
                .baseUrl(baseUrl)
                .build();

        OpenAiEmbeddingOptions options = OpenAiEmbeddingOptions.builder()
                .model(model)
                .build();

        embeddingModel = new OpenAiEmbeddingModel(openAiApi, MetadataMode.EMBED, options);
        log.info("Embedding 初始化完成: model={}, baseUrl={}", model, baseUrl);
    }

    public List<Float> embed(String text) {
        if (embeddingModel == null) {
            throw new IllegalStateException("Embedding 未初始化，请检查 knowledge-base.embedding.api-key 配置");
        }
        float[] vector = embeddingModel.embed(text);
        // float[] → List<Float>
        List<Float> result = new java.util.ArrayList<>(vector.length);
        for (float v : vector) {
            result.add(v);
        }
        return result;
    }
}
