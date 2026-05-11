package com.example.classification.knowledge;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchResponse;
import co.elastic.clients.elasticsearch.core.search.Hit;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.StringReader;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 知识库 ES 检索工具（3 个 @Tool 方法供 Agent 调用）
 */
@Slf4j
@Component
public class KnowledgeBaseSearchTool {

    private final ElasticsearchClient esClient;
    private final EmbeddingHelper embeddingHelper;

    @Value("${knowledge-base.es-index:kb-chunks}")
    private String indexName;

    public KnowledgeBaseSearchTool(ElasticsearchClient esClient, EmbeddingHelper embeddingHelper) {
        this.esClient = esClient;
        this.embeddingHelper = embeddingHelper;
    }

    @Tool(description = "BM25关键词搜索知识库，适合查具体术语、字段名、安全级别编号等。返回最相关的知识库片段。")
    public String keywordSearch(
            @ToolParam(description = "搜索关键词，如'银行卡密码 安全级别'或'C3类别信息'") String query,
            @ToolParam(description = "返回结果数量，默认5") int topK) {

        if (topK <= 0) topK = 5;
        log.debug("keywordSearch: query='{}', topK={}", query, topK);

        try {
            int finalTopK = topK;
            SearchResponse<Map> resp = esClient.search(s -> s
                    .index(indexName)
                    .size(finalTopK)
                    .query(q -> q.match(m -> m
                            .field("content")
                            .query(query)
                            .analyzer("ik_smart")
                    )), Map.class);

            return formatHits(resp.hits().hits());
        } catch (Exception e) {
            log.error("keywordSearch 失败: {}", e.getMessage());
            return "搜索失败: " + e.getMessage();
        }
    }

    @Tool(description = "语义向量搜索知识库，适合模糊意图、换了说法的查询、跨章节关联检索。返回语义最相近的知识库片段。")
    public String semanticSearch(
            @ToolParam(description = "自然语言查询，如'个人隐私在传输过程中如何保护'") String query,
            @ToolParam(description = "返回结果数量，默认5") int topK) {

        if (topK <= 0) topK = 5;
        log.debug("semanticSearch: query='{}', topK={}", query, topK);

        try {
            List<Float> vector = embeddingHelper.embed(query);
            int finalTopK = topK;

            // 使用原始 JSON 构建 knn 查询
            String knnJson = String.format("""
                    {
                      "size": %d,
                      "knn": {
                        "field": "embedding",
                        "query_vector": %s,
                        "k": %d,
                        "num_candidates": %d
                      }
                    }
                    """, finalTopK, vector.toString(), finalTopK, finalTopK * 10);

            SearchResponse<Map> resp = esClient.search(s -> s
                    .index(indexName)
                    .withJson(new StringReader(knnJson)), Map.class);

            return formatHits(resp.hits().hits());
        } catch (Exception e) {
            log.error("semanticSearch 失败: {}", e.getMessage());
            return "搜索失败: " + e.getMessage();
        }
    }

    @Tool(description = "按标准名和章节名拉取整个章节的全部内容。适合需要通读某个标准的正文或附录时使用。standard和section参数需从知识库目录中选取。")
    public String retrieveSection(
            @ToolParam(description = "标准名，如'JRT-0171-2020-个人金融信息保护技术规范'或'JRT-0197-2020-金融数据安全分级指南'") String standard,
            @ToolParam(description = "章节名，如'正文-安全技术要求'或'附录A-经营管理数据'") String section) {

        log.debug("retrieveSection: standard='{}', section='{}'", standard, section);

        try {
            SearchResponse<Map> resp = esClient.search(s -> s
                    .index(indexName)
                    .size(100)
                    .query(q -> q.bool(b -> b
                            .filter(f -> f.term(t -> t.field("standard").value(standard)))
                            .filter(f -> f.term(t -> t.field("section").value(section)))
                    ))
                    .sort(so -> so.field(f -> f.field("chunk_range").order(co.elastic.clients.elasticsearch._types.SortOrder.Asc))),
                    Map.class);

            List<Hit<Map>> hits = resp.hits().hits();
            if (hits.isEmpty()) {
                return "未找到章节: " + standard + "/" + section;
            }

            return hits.stream()
                    .map(h -> {
                        Map<String, Object> src = h.source();
                        return "【" + src.get("path") + "】\n" + src.get("content");
                    })
                    .collect(Collectors.joining("\n\n==========\n\n"));
        } catch (Exception e) {
            log.error("retrieveSection 失败: {}", e.getMessage());
            return "检索失败: " + e.getMessage();
        }
    }

    private String formatHits(List<Hit<Map>> hits) {
        if (hits.isEmpty()) {
            return "未找到相关内容。";
        }
        return hits.stream()
                .map(h -> {
                    Map<String, Object> src = h.source();
                    double score = h.score() != null ? h.score() : 0;
                    return String.format("【%s】(score=%.4f)\n%s", src.get("path"), score, src.get("content"));
                })
                .collect(Collectors.joining("\n\n==========\n\n"));
    }
}
