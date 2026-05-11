package com.example.classification.knowledge;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.json.jackson.JacksonJsonpMapper;
import co.elastic.clients.transport.rest_client.RestClientTransport;
import lombok.extern.slf4j.Slf4j;
import org.apache.http.HttpHost;
import org.elasticsearch.client.RestClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Elasticsearch 客户端配置
 */
@Slf4j
@Configuration
public class ElasticsearchConfig {

    @Value("${knowledge-base.es-url:http://localhost:9200}")
    private String esUrl;

    @Bean
    public RestClient elasticsearchRestClient() {
        return RestClient.builder(HttpHost.create(esUrl)).build();
    }

    @Bean
    public ElasticsearchClient elasticsearchClient(RestClient restClient) {
        RestClientTransport transport = new RestClientTransport(restClient, new JacksonJsonpMapper());
        log.info("ES 客户端初始化: {}", esUrl);
        return new ElasticsearchClient(transport);
    }
}
