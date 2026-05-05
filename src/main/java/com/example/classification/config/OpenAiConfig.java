package com.example.classification.config;

import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
public class OpenAiConfig {

    /**
     * 根据多模型配置创建 ChatModel，使用 active 指定的模型
     */
    @Bean
    @Primary
    public OpenAiChatModel openAiChatModel(ModelsProperties modelsProperties) {
        ModelConfig activeConfig = modelsProperties.getActiveConfig();
        if (activeConfig == null) {
            throw new IllegalStateException("未配置任何模型，请检查 application.yml 中的 models.configs");
        }

        OpenAiApi openAiApi = OpenAiApi.builder()
                .apiKey(activeConfig.getApiKey())
                .baseUrl(activeConfig.getBaseUrl())
                .build();

        OpenAiChatOptions options = OpenAiChatOptions.builder()
                .model(activeConfig.getModel())
                .temperature(0.1)
                .maxTokens(1024)
                .build();

        return OpenAiChatModel.builder()
                .openAiApi(openAiApi)
                .defaultOptions(options)
                .build();
    }
}
