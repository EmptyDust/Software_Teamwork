package adapter

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Sakayori-Iroha-168/Software_Teamwork/services/knowledge/internal/service"
	"github.com/Sakayori-Iroha-168/Software_Teamwork/services/knowledge/internal/vendorclient"
)

const defaultMaxUploadBytes = int64(32 << 20)
const defaultMaxJSONBodyBytes = int64(1 << 20)

const (
	documentBatchMaxFiles             = 10
	documentBatchMultipartMemoryBytes = defaultMaxUploadBytes
	documentBatchMultipartOverhead    = int64(4 << 20)
	documentBatchMaxUploadBytes       = defaultMaxUploadBytes*documentBatchMaxFiles + documentBatchMultipartOverhead
)

const documentDeletionJobMaxDocuments = 100

const (
	vendorRetCodeArgument       = 101
	vendorRetCodePermission     = 108
	vendorRetCodeAuthentication = 109
)

const (
	ragflowLayoutDeepDOC        = "DeepDOC"
	ragflowLayoutPaddleOCR      = "PaddleOCR"
	ragflowLayoutMinerU         = "MinerU"
	ragflowLayoutOpenDataLoader = "OpenDataLoader"
	ragflowLayoutPlainText      = "Plain Text"

	parserConfigTraceKey             = "software_teamwork_parser_config"
	parserConfigCredentialsKey       = "software_teamwork_parser_config_credentials"
	runtimeManagedTraceValue         = "runtime-managed"
	runtimeManagedEmbeddingDimension = -1
)

var publicStandardMetadataKeys = map[string]string{
	"standard_no_kwd":   "standardNo",
	"standard_year_int": "standardYear",
	"clause_no_kwd":     "clauseNo",
	"clause_title_tks":  "clauseTitle",
	"table_no_kwd":      "tableNo",
	"table_title_tks":   "tableTitle",
	"row_index_int":     "rowIndex",
	"columns_obj":       "columns",
}

type knowledgeBaseSummary struct {
	ID                string          `json:"id"`
	Name              string          `json:"name"`
	Description       string          `json:"description"`
	DocType           string          `json:"docType"`
	ChunkStrategy     json.RawMessage `json:"chunkStrategy"`
	RetrievalStrategy json.RawMessage `json:"retrievalStrategy"`
	DocumentCount     int64           `json:"documentCount"`
	ChunkCount        int64           `json:"chunkCount"`
	CreatedBy         string          `json:"createdBy,omitempty"`
	CreatedAt         time.Time       `json:"createdAt"`
	UpdatedAt         time.Time       `json:"updatedAt"`
}

type createKnowledgeBaseRequest struct {
	ID                *string          `json:"id"`
	Name              string           `json:"name"`
	Description       *string          `json:"description"`
	DocType           *string          `json:"docType"`
	ChunkStrategy     *json.RawMessage `json:"chunkStrategy"`
	RetrievalStrategy *json.RawMessage `json:"retrievalStrategy"`
}

type updateKnowledgeBaseRequest struct {
	Name              *string          `json:"name"`
	Description       *string          `json:"description"`
	DocType           *string          `json:"docType"`
	ChunkStrategy     *json.RawMessage `json:"chunkStrategy"`
	RetrievalStrategy *json.RawMessage `json:"retrievalStrategy"`
	ParserConfigID    *string          `json:"parserConfigId"`
}

type updateDocumentRequest struct {
	Tags *[]string `json:"tags"`
}

type createDocumentDeletionJobRequest struct {
	DocumentIDs []string `json:"documentIds"`
}

type knowledgeQueryRequest struct {
	Query            string            `json:"query"`
	KnowledgeBaseIDs []string          `json:"knowledgeBaseIds,omitempty"`
	DocumentIDs      []string          `json:"documentIds,omitempty"`
	TopK             int               `json:"topK,omitempty"`
	ScoreThreshold   *float64          `json:"scoreThreshold,omitempty"`
	Tags             []string          `json:"tags,omitempty"`
	MetadataFilter   map[string]string `json:"metadataFilter,omitempty"`
	Rerank           bool              `json:"rerank,omitempty"`
	RerankTopN       *int              `json:"rerankTopN,omitempty"`
}

type retrievalBuildOptions struct {
	VendorRerankID string
}

type createDatasetOptions struct {
	VendorEmbeddingID string
}

type knowledgeQueryTraceOptions struct {
	VendorEmbeddingID string
}

type knowledgeQuerySummary struct {
	ID      string                 `json:"id"`
	Query   string                 `json:"query"`
	Results []knowledgeQueryResult `json:"results"`
	Trace   knowledgeQueryTrace    `json:"trace"`
}

type knowledgeQueryResult struct {
	Score           float64  `json:"score"`
	KnowledgeBaseID string   `json:"knowledgeBaseId"`
	DocumentID      string   `json:"documentId"`
	ChunkID         string   `json:"chunkId"`
	DocumentName    string   `json:"documentName"`
	SectionPath     *string  `json:"sectionPath,omitempty"`
	ChunkIndex      *int     `json:"chunkIndex,omitempty"`
	ChunkType       *string  `json:"chunkType,omitempty"`
	ContentPreview  string   `json:"contentPreview"`
	Tags            []string `json:"tags,omitempty"`
}

type knowledgeQueryTrace struct {
	EmbeddingProvider  string  `json:"embeddingProvider"`
	EmbeddingModel     string  `json:"embeddingModel"`
	EmbeddingDimension int     `json:"embeddingDimension"`
	SearchTopK         int     `json:"searchTopK"`
	ScoreThreshold     float64 `json:"scoreThreshold"`
	HitCount           int     `json:"hitCount"`
	Rerank             bool    `json:"rerank"`
	RerankTopN         *int    `json:"rerankTopN,omitempty"`
}

type knowledgeStatisticsSummary struct {
	KnowledgeBaseCount int64                     `json:"knowledgeBaseCount"`
	DocumentCount      int64                     `json:"documentCount"`
	ChunkCount         int64                     `json:"chunkCount"`
	Series             knowledgeStatisticsSeries `json:"series"`
}

type knowledgeStatisticsSeries struct {
	KnowledgeBaseCount []knowledgeStatisticsPoint `json:"knowledgeBaseCount"`
	DocumentCount      []knowledgeStatisticsPoint `json:"documentCount"`
	ChunkCount         []knowledgeStatisticsPoint `json:"chunkCount"`
}

type knowledgeStatisticsPoint struct {
	Date  time.Time `json:"date"`
	Count int64     `json:"count"`
}

type documentSummary struct {
	ID              string                 `json:"id"`
	KnowledgeBaseID string                 `json:"knowledgeBaseId"`
	Name            string                 `json:"name"`
	ContentType     *string                `json:"contentType,omitempty"`
	SizeBytes       *int64                 `json:"sizeBytes,omitempty"`
	Status          service.DocumentStatus `json:"status"`
	ErrorCode       *string                `json:"errorCode,omitempty"`
	ErrorMessage    *string                `json:"errorMessage,omitempty"`
	ChunkCount      int64                  `json:"chunkCount"`
	Tags            []string               `json:"tags,omitempty"`
	ParserBackend   *string                `json:"parserBackend,omitempty"`
	CreatedBy       string                 `json:"createdBy,omitempty"`
	CreatedAt       time.Time              `json:"createdAt"`
	UpdatedAt       time.Time              `json:"updatedAt"`
	JobID           *string                `json:"jobId,omitempty"`
}

type documentBatchSummary struct {
	TotalCount   int                 `json:"totalCount"`
	SuccessCount int                 `json:"successCount"`
	FailedCount  int                 `json:"failedCount"`
	Results      []documentBatchItem `json:"results"`
}

type documentBatchItem struct {
	Filename string                  `json:"filename"`
	Status   string                  `json:"status"`
	Document *documentSummary        `json:"document,omitempty"`
	Error    *documentBatchItemError `json:"error,omitempty"`
}

type documentBatchItemError struct {
	Code    service.Code `json:"code"`
	Message string       `json:"message"`
}

type documentDeletionJobSummary struct {
	ID              string                      `json:"id"`
	Status          string                      `json:"status"`
	KnowledgeBaseID string                      `json:"knowledgeBaseId"`
	TargetIDs       []string                    `json:"targetIds"`
	TotalCount      int                         `json:"totalCount"`
	SuccessCount    int                         `json:"successCount"`
	FailedCount     int                         `json:"failedCount"`
	Results         []documentDeletionJobResult `json:"results"`
}

type documentDeletionJobResult struct {
	DocumentID string                        `json:"documentId"`
	Status     string                        `json:"status"`
	Error      *documentDeletionJobItemError `json:"error,omitempty"`
}

type documentDeletionJobItemError struct {
	Code    service.Code `json:"code"`
	Message string       `json:"message"`
}

type documentChunkSummary struct {
	ID                string         `json:"id"`
	KnowledgeBaseID   string         `json:"knowledgeBaseId"`
	DocumentID        string         `json:"documentId"`
	ChunkIndex        int32          `json:"chunkIndex"`
	SectionPath       *string        `json:"sectionPath,omitempty"`
	Content           string         `json:"content"`
	ChunkType         *string        `json:"chunkType,omitempty"`
	EmbeddingProvider *string        `json:"embeddingProvider,omitempty"`
	Metadata          map[string]any `json:"metadata,omitempty"`
	CreatedAt         time.Time      `json:"createdAt"`
}

func mapVendorError(err error) error {
	if err == nil {
		return nil
	}
	var apiErr *vendorclient.APIError
	if errors.As(err, &apiErr) {
		msg := strings.TrimSpace(apiErr.Message)
		switch {
		case apiErr.MatchesHTTPStatus(http.StatusBadRequest) || apiErr.Code == http.StatusBadRequest || apiErr.Code == vendorRetCodeArgument:
			if msg == "" {
				msg = "vendor runtime validation failed"
			}
			return service.ValidationError(msg, nil)
		case apiErr.MatchesHTTPStatus(http.StatusUnauthorized) ||
			apiErr.Code == http.StatusUnauthorized ||
			apiErr.Code == vendorRetCodeAuthentication:
			if msg == "" {
				msg = "vendor runtime authentication failed"
			}
			return service.DependencyError(msg, err)
		case apiErr.MatchesHTTPStatus(http.StatusForbidden) || apiErr.Code == http.StatusForbidden || apiErr.Code == vendorRetCodePermission:
			return service.ForbiddenError(msg)
		case apiErr.MatchesHTTPStatus(http.StatusNotFound) || apiErr.Code == http.StatusNotFound:
			if msg == "" {
				msg = "resource not found"
			}
			return service.NotFoundError(msg)
		}
		if msg == "" {
			msg = "vendor runtime request failed"
		}
		return service.DependencyError(msg, err)
	}
	return service.DependencyError("vendor runtime request failed", err)
}

func knowledgeBaseFromVendor(raw map[string]interface{}) knowledgeBaseSummary {
	chunkStrategy := json.RawMessage(`{}`)
	if cfg := raw["parser_config"]; cfg != nil {
		if encoded, err := json.Marshal(cfg); err == nil {
			chunkStrategy = encoded
		}
	}
	retrievalStrategy := json.RawMessage(`{}`)
	retrieval := map[string]any{}
	if v, ok := raw["similarity_threshold"]; ok {
		retrieval["scoreThreshold"] = v
	}
	if v, ok := raw["vector_similarity_weight"]; ok {
		retrieval["vectorWeight"] = v
	}
	if len(retrieval) > 0 {
		if encoded, err := json.Marshal(retrieval); err == nil {
			retrievalStrategy = encoded
		}
	}
	description := stringField(raw, "description")
	docType := stringField(raw, "chunk_method")
	if docType == "" {
		docType = stringField(raw, "parser_id")
	}
	return knowledgeBaseSummary{
		ID:                stringField(raw, "id"),
		Name:              stringField(raw, "name"),
		Description:       description,
		DocType:           docType,
		ChunkStrategy:     chunkStrategy,
		RetrievalStrategy: retrievalStrategy,
		DocumentCount:     int64Field(raw, "document_count", "doc_num"),
		ChunkCount:        int64Field(raw, "chunk_count", "chunk_num"),
		CreatedBy:         stringField(raw, "created_by"),
		CreatedAt:         timeField(raw, "create_time", "created_at", "create_date"),
		UpdatedAt:         timeField(raw, "update_time", "updated_at", "update_date"),
	}
}

func knowledgeBasesFromVendor(items []map[string]interface{}) []knowledgeBaseSummary {
	out := make([]knowledgeBaseSummary, 0, len(items))
	for _, item := range items {
		out = append(out, knowledgeBaseFromVendor(item))
	}
	return out
}

func documentFromVendor(raw map[string]interface{}) documentSummary {
	kbID := stringField(raw, "dataset_id", "kb_id")
	name := stringField(raw, "name")
	contentType := normalizedDocumentContentType(raw)
	size := optionalInt64Field(raw, "size")
	status := mapDocumentStatus(raw)
	parserBackend := optionalStringField(raw, "chunk_method", "parser_id")
	progressMsg := optionalStringField(raw, "progress_msg")
	var errorCode *string
	var errorMessage *string
	if status == service.DocumentStatusFailed && progressMsg != nil {
		errorMessage = progressMsg
		code := string(service.CodeDependency)
		errorCode = &code
	}
	return documentSummary{
		ID:              stringField(raw, "id"),
		KnowledgeBaseID: kbID,
		Name:            name,
		ContentType:     contentType,
		SizeBytes:       size,
		Status:          status,
		ErrorCode:       errorCode,
		ErrorMessage:    errorMessage,
		ChunkCount:      int64Field(raw, "chunk_count", "chunk_num"),
		Tags:            tagsFromVendor(raw),
		ParserBackend:   parserBackend,
		CreatedBy:       stringField(raw, "created_by"),
		CreatedAt:       timeField(raw, "create_time", "created_at", "create_date"),
		UpdatedAt:       timeField(raw, "update_time", "updated_at", "update_date"),
	}
}

func documentsFromVendor(items []map[string]interface{}) []documentSummary {
	out := make([]documentSummary, 0, len(items))
	for _, item := range items {
		out = append(out, documentFromVendor(item))
	}
	return out
}

func documentChunkFromVendor(raw map[string]interface{}, kbID, documentID string, fallbackIndex int) documentChunkSummary {
	content := stringField(raw, "content_with_weight", "content")
	if content == "" {
		content = stringField(raw, "content_ltks")
	}
	chunkIndex := int32(fallbackIndex)
	if explicitIndex := optionalIntField(raw, "chunk_index", "chunkIndex"); explicitIndex != nil {
		chunkIndex = int32(*explicitIndex)
	}
	return documentChunkSummary{
		ID:                stringField(raw, "id", "chunk_id"),
		KnowledgeBaseID:   firstNonEmpty(stringField(raw, "kb_id", "dataset_id"), kbID),
		DocumentID:        firstNonEmpty(stringField(raw, "doc_id", "document_id"), documentID),
		ChunkIndex:        chunkIndex,
		SectionPath:       sectionPathFromVendor(raw),
		Content:           content,
		ChunkType:         optionalStringField(raw, "chunk_type", "chunkType", "doc_type_kwd"),
		EmbeddingProvider: embeddingProviderField(raw),
		Metadata:          publicMetadataFromVendor(raw),
		CreatedAt:         timeField(raw, "create_time", "created_at"),
	}
}

func documentChunksFromVendor(items []map[string]interface{}, kbID, documentID string, fallbackStart int) []documentChunkSummary {
	out := make([]documentChunkSummary, 0, len(items))
	for idx, item := range items {
		out = append(out, documentChunkFromVendor(item, kbID, documentID, fallbackStart+idx))
	}
	return out
}

func knowledgeQueryFromVendor(queryID, query string, data *vendorclient.RetrievalData, topK int, scoreThreshold float64, rerank bool, rerankTopN *int, opts knowledgeQueryTraceOptions) knowledgeQuerySummary {
	results := make([]knowledgeQueryResult, 0)
	if data != nil {
		for _, chunk := range data.Chunks {
			results = append(results, mapRetrievalChunk(chunk))
		}
	}
	hitCount := len(results)
	if data != nil && data.Total > 0 {
		hitCount = int(data.Total)
	}
	return knowledgeQuerySummary{
		ID:      queryID,
		Query:   query,
		Results: results,
		Trace: knowledgeQueryTrace{
			EmbeddingProvider:  "runtime",
			EmbeddingModel:     firstNonEmpty(strings.TrimSpace(opts.VendorEmbeddingID), runtimeManagedTraceValue),
			EmbeddingDimension: runtimeManagedEmbeddingDimension,
			SearchTopK:         topK,
			ScoreThreshold:     scoreThreshold,
			HitCount:           hitCount,
			Rerank:             rerank,
			RerankTopN:         rerankTopN,
		},
	}
}

func mapRetrievalChunk(raw map[string]interface{}) knowledgeQueryResult {
	score := floatField(raw, "similarity", "score", "vector_similarity")
	kbID := stringField(raw, "kb_id", "dataset_id")
	docID := stringField(raw, "doc_id", "document_id")
	chunkID := stringField(raw, "chunk_id", "id")
	docName := stringField(raw, "docnm_kwd", "document_name", "doc_name")
	content := retrievalContentPreview(stringField(raw, "content_with_weight", "content"))
	var chunkIndex *int
	if idx := optionalIntField(raw, "chunk_index", "page_num_int"); idx != nil && *idx >= 0 {
		chunkIndex = idx
	}
	return knowledgeQueryResult{
		Score:           score,
		KnowledgeBaseID: kbID,
		DocumentID:      docID,
		ChunkID:         chunkID,
		DocumentName:    docName,
		SectionPath:     sectionPathFromVendor(raw),
		ChunkIndex:      chunkIndex,
		ChunkType:       optionalStringField(raw, "chunk_type", "chunkType", "doc_type_kwd"),
		ContentPreview:  content,
		Tags:            stringSliceField(raw, "tag_kwd", "tags"),
	}
}

func retrievalContentPreview(content string) string {
	if len(content) <= 240 {
		return content
	}
	return strings.ToValidUTF8(content[:240], "")
}

func buildCreateDatasetBody(req createKnowledgeBaseRequest, defaultParserConfig map[string]any, opts createDatasetOptions) ([]byte, error) {
	payload := map[string]any{
		"name": strings.TrimSpace(req.Name),
	}
	if embeddingID := strings.TrimSpace(opts.VendorEmbeddingID); embeddingID != "" {
		payload["embedding_model"] = embeddingID
	}
	if req.Description != nil {
		payload["description"] = strings.TrimSpace(*req.Description)
	}
	if req.DocType != nil && strings.TrimSpace(*req.DocType) != "" {
		payload["chunk_method"] = strings.TrimSpace(*req.DocType)
	}
	if req.ChunkStrategy != nil {
		var cfg map[string]any
		if err := json.Unmarshal(*req.ChunkStrategy, &cfg); err != nil || cfg == nil {
			return nil, service.ValidationError("request validation failed", map[string]string{"chunkStrategy": "must be a valid JSON object"})
		}
		payload["parser_config"] = cfg
	} else if len(defaultParserConfig) > 0 {
		payload["parser_config"] = vendorParserConfig(defaultParserConfig)
		if credentials := parserConfigCredentials(defaultParserConfig); len(credentials) > 0 {
			payload["parser_config_credentials"] = credentials
		}
	}
	return json.Marshal(payload)
}

func vendorParserConfig(in map[string]any) map[string]any {
	if len(in) == 0 {
		return nil
	}
	out := make(map[string]any, len(in))
	for key, value := range in {
		if key == parserConfigTraceKey || key == parserConfigCredentialsKey {
			continue
		}
		out[key] = value
	}
	return out
}

func parserConfigCredentials(in map[string]any) map[string]any {
	if len(in) == 0 {
		return nil
	}
	raw, ok := in[parserConfigCredentialsKey].(map[string]any)
	if !ok || len(raw) == 0 {
		return nil
	}
	return cloneAnyMap(raw)
}

func buildUpdateDatasetBody(req updateKnowledgeBaseRequest, parserConfig map[string]any) ([]byte, error) {
	payload := map[string]any{}
	if req.Name != nil {
		payload["name"] = strings.TrimSpace(*req.Name)
	}
	if req.Description != nil {
		payload["description"] = strings.TrimSpace(*req.Description)
	}
	if req.DocType != nil {
		payload["chunk_method"] = strings.TrimSpace(*req.DocType)
	}
	if len(parserConfig) > 0 {
		payload["parser_config"] = vendorParserConfig(parserConfig)
		if credentials := parserConfigCredentials(parserConfig); len(credentials) > 0 {
			payload["parser_config_credentials"] = credentials
		}
	}
	if req.ChunkStrategy != nil {
		var cfg map[string]any
		if err := json.Unmarshal(*req.ChunkStrategy, &cfg); err != nil || cfg == nil {
			return nil, service.ValidationError("request validation failed", map[string]string{"chunkStrategy": "must be a valid JSON object"})
		}
		if existing, ok := payload["parser_config"].(map[string]any); ok {
			for key, value := range cfg {
				existing[key] = value
			}
			payload["parser_config"] = existing
		} else {
			payload["parser_config"] = cfg
		}
	}
	if len(payload) == 0 {
		return nil, service.ValidationError("request validation failed", map[string]string{"body": "must include at least one supported field"})
	}
	return json.Marshal(payload)
}

func ragflowParserConfigFromSnapshot(snapshot service.ParserConfigSnapshot) map[string]any {
	defaultParameters := parserParameterObject(snapshot.DefaultParameters)
	layoutRecognize := ragflowLayoutFromParserConfig(snapshot, defaultParameters)
	cfg := map[string]any{}
	for key, value := range defaultParameters {
		key = normalizeParserParameterKey(key)
		if key == "" || key == "layout_recognize" || isSensitiveParserParameter(key) || isPaddleOCRCloudParameter(key) {
			continue
		}
		if sanitized, ok := sanitizeParserParameterValue(value); ok {
			cfg[key] = sanitized
		}
	}
	cfg["layout_recognize"] = layoutRecognize
	if snapshot.Backend == service.ParserBackendPaddleOCRCloud {
		if credentials := paddleOCRCloudCredentials(defaultParameters); len(credentials) > 0 {
			cfg[parserConfigCredentialsKey] = credentials
		}
	}
	cfg[parserConfigTraceKey] = parserConfigTrace(snapshot, layoutRecognize)
	return cfg
}

func paddleOCRCloudCredentials(defaultParameters map[string]any) map[string]any {
	accessToken := parserParameterString(defaultParameters, service.PaddleOCRAccessTokenParameter)
	if accessToken == "" {
		return nil
	}
	baseURL := parserParameterString(defaultParameters, service.PaddleOCRBaseURLParameter)
	algorithm := parserParameterString(defaultParameters, service.PaddleOCRAlgorithmParameter)
	if algorithm == "" {
		algorithm = service.PaddleOCRDefaultModel
	}
	return map[string]any{
		"paddleocr_cloud": map[string]any{
			service.PaddleOCRBaseURLParameter:     baseURL,
			service.PaddleOCRAccessTokenParameter: accessToken,
			service.PaddleOCRAlgorithmParameter:   algorithm,
		},
	}
}

func ragflowLayoutFromParserConfig(snapshot service.ParserConfigSnapshot, defaultParameters map[string]any) string {
	switch snapshot.Backend {
	case service.ParserBackendBuiltin:
		return ragflowLayoutDeepDOC
	case service.ParserBackendLocalOCR, service.ParserBackendPaddleOCRCloud:
		return ragflowLayoutPaddleOCR
	case service.ParserBackendRemoteCompatible:
		if layout := parserParameterString(defaultParameters, "layout_recognize", "layoutRecognize", "layoutRecognizer"); layout != "" {
			return layout
		}
		return ragflowLayoutPaddleOCR
	case service.ParserBackendTika, service.ParserBackendUnstructured:
		return ragflowLayoutPlainText
	default:
		return ragflowLayoutDeepDOC
	}
}

func parserConfigTrace(snapshot service.ParserConfigSnapshot, layoutRecognize string) map[string]any {
	trace := map[string]any{
		"backend":         string(snapshot.Backend),
		"layoutRecognize": layoutRecognize,
		"concurrency":     snapshot.Concurrency,
	}
	if strings.TrimSpace(snapshot.ParserConfigID) != "" {
		trace["parserConfigId"] = strings.TrimSpace(snapshot.ParserConfigID)
	}
	if len(snapshot.SupportedContentTypes) > 0 {
		trace["supportedContentTypes"] = append([]string(nil), snapshot.SupportedContentTypes...)
	}
	if snapshot.EndpointURL != nil && strings.TrimSpace(*snapshot.EndpointURL) != "" {
		trace["endpointUrl"] = strings.TrimSpace(*snapshot.EndpointURL)
	}
	return trace
}

func parserParameterObject(raw json.RawMessage) map[string]any {
	if len(raw) == 0 {
		return nil
	}
	var params map[string]any
	if err := json.Unmarshal(raw, &params); err != nil {
		return nil
	}
	return params
}

func parserParameterString(params map[string]any, keys ...string) string {
	for _, key := range keys {
		value, ok := params[key]
		if !ok {
			continue
		}
		raw, ok := value.(string)
		if !ok {
			continue
		}
		if trimmed := strings.TrimSpace(raw); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func normalizeParserParameterKey(key string) string {
	switch strings.TrimSpace(key) {
	case "layoutRecognize", "layoutRecognizer":
		return "layout_recognize"
	default:
		return strings.TrimSpace(key)
	}
}

func isSensitiveParserParameter(key string) bool {
	return service.IsSensitiveParserParameterKey(key)
}

func isPaddleOCRCloudParameter(key string) bool {
	switch key {
	case service.PaddleOCRBaseURLParameter, service.PaddleOCRAccessTokenParameter, service.PaddleOCRAlgorithmParameter:
		return true
	default:
		return false
	}
}

func sanitizeParserParameterValue(value any) (any, bool) {
	switch typed := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, value := range typed {
			key = normalizeParserParameterKey(key)
			if key == "" || isSensitiveParserParameter(key) {
				continue
			}
			if sanitized, ok := sanitizeParserParameterValue(value); ok {
				out[key] = sanitized
			}
		}
		return out, true
	case []any:
		out := make([]any, 0, len(typed))
		for _, item := range typed {
			if sanitized, ok := sanitizeParserParameterValue(item); ok {
				out = append(out, sanitized)
			}
		}
		return out, true
	default:
		return value, true
	}
}

func cloneAnyMap(in map[string]any) map[string]any {
	if len(in) == 0 {
		return nil
	}
	out := make(map[string]any, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}

func buildUpdateDocumentBody(tags []string) ([]byte, error) {
	return json.Marshal(map[string]any{
		"meta_fields": map[string]any{"tags": tags},
	})
}

func tagsFromVendor(raw map[string]interface{}) []string {
	metaFields, ok := raw["meta_fields"].(map[string]interface{})
	if !ok {
		return nil
	}
	tagsVal, ok := metaFields["tags"]
	if !ok || tagsVal == nil {
		return nil
	}
	switch typed := tagsVal.(type) {
	case []string:
		return typed
	case []interface{}:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			if value := strings.TrimSpace(fmt.Sprint(item)); value != "" {
				out = append(out, value)
			}
		}
		return out
	default:
		return nil
	}
}

func sectionPathFromVendor(raw map[string]interface{}) *string {
	if value := stringField(raw, "section_path", "sectionPath", "section_path_kwd"); value != "" {
		return &value
	}
	for _, nested := range nestedMaps(raw, "metadata", "meta", "extra", "metadata_obj", "metadataObject") {
		if value := stringField(nested, "section_path", "sectionPath", "section_path_kwd"); value != "" {
			return &value
		}
	}
	return nil
}

func publicMetadataFromVendor(raw map[string]interface{}) map[string]any {
	metadata := map[string]any{}
	for key, value := range raw {
		publicKey, isStandardMetadata := publicStandardMetadataKeys[key]
		if !isStandardMetadata {
			publicKey = key
		}
		if shouldSkipChunkMetadata(key) {
			continue
		}
		metadata[publicKey] = value
	}
	for runtimeKey, publicKey := range publicStandardMetadataKeys {
		if value, ok := raw[runtimeKey]; ok && value != nil {
			metadata[publicKey] = value
		}
	}
	for _, nested := range nestedMaps(raw, "metadata", "meta", "extra", "metadata_obj", "metadataObject") {
		for runtimeKey, publicKey := range publicStandardMetadataKeys {
			if _, exists := metadata[publicKey]; exists {
				continue
			}
			if value, ok := nested[runtimeKey]; ok && value != nil {
				metadata[publicKey] = value
			}
		}
	}
	if len(metadata) == 0 {
		return nil
	}
	return metadata
}

func shouldSkipChunkMetadata(key string) bool {
	if isRuntimeVectorField(key) {
		return true
	}
	if _, ok := publicStandardMetadataKeys[key]; ok {
		return true
	}
	switch key {
	case "id", "chunk_id", "content_with_weight", "content", "content_ltks", "chunk_index", "chunkIndex", "page_num_int", "doc_id", "document_id", "kb_id", "dataset_id", "docnm_kwd", "image_id", "img_id", "available", "available_int", "positions", "position_int", "tag_kwd", "tag_feas", "important_kwd", "question_kwd", "section_path", "sectionPath", "section_path_kwd", "chunk_type", "chunkType", "doc_type_kwd", "metadata", "meta", "extra", "metadata_obj", "metadataObject", "vector", "token_count", "tokenCount", "token_num", "embedding_provider", "embeddingProvider", "embedding_model", "embeddingModel", "embd_id", "embedding_dimension_int", "embedding_dimension", "embeddingDimension", "vector_dim", "vectorDim", "object_key", "provider_response", "access_token":
		return true
	default:
		return false
	}
}

func nestedMaps(raw map[string]interface{}, keys ...string) []map[string]interface{} {
	out := make([]map[string]interface{}, 0, len(keys))
	for _, key := range keys {
		value, ok := raw[key]
		if !ok || value == nil {
			continue
		}
		if nested, ok := value.(map[string]interface{}); ok {
			out = append(out, nested)
		}
	}
	return out
}

func stringSliceField(raw map[string]interface{}, keys ...string) []string {
	for _, key := range keys {
		value, ok := raw[key]
		if !ok || value == nil {
			continue
		}
		switch typed := value.(type) {
		case []string:
			return append([]string(nil), typed...)
		case []interface{}:
			out := make([]string, 0, len(typed))
			for _, item := range typed {
				if value := strings.TrimSpace(fmt.Sprint(item)); value != "" {
					out = append(out, value)
				}
			}
			return out
		default:
			value := strings.TrimSpace(fmt.Sprint(typed))
			if value != "" {
				return []string{value}
			}
		}
	}
	return nil
}

func buildRetrievalBody(req knowledgeQueryRequest, opts retrievalBuildOptions) ([]byte, error) {
	query := strings.TrimSpace(req.Query)
	if query == "" {
		return nil, service.ValidationError("request validation failed", map[string]string{"query": "is required"})
	}
	if len(req.KnowledgeBaseIDs) == 0 {
		return nil, service.ValidationError("request validation failed", map[string]string{"knowledgeBaseIds": "must include at least one knowledge base id"})
	}
	topK := req.TopK
	if topK <= 0 {
		topK = 10
	}
	payload := map[string]any{
		"question":    query,
		"dataset_ids": req.KnowledgeBaseIDs,
		"top_k":       topK,
		"size":        topK,
	}
	if req.ScoreThreshold != nil {
		payload["similarity_threshold"] = *req.ScoreThreshold
	}
	if len(req.DocumentIDs) > 0 {
		payload["doc_ids"] = req.DocumentIDs
	}
	if filter := vendorMetaDataFilter(req); filter != nil {
		payload["meta_data_filter"] = filter
	}
	if req.Rerank {
		if rerankID := strings.TrimSpace(opts.VendorRerankID); rerankID != "" {
			payload["rerank_id"] = rerankID
		}
		if req.RerankTopN != nil && *req.RerankTopN > 0 {
			size := *req.RerankTopN
			if size > topK {
				size = topK
			}
			payload["size"] = size
		}
	}
	return json.Marshal(payload)
}

func documentVendorWithTags(raw map[string]interface{}, tags []string) map[string]interface{} {
	out := make(map[string]interface{}, len(raw)+1)
	for key, value := range raw {
		out[key] = value
	}
	metaFields := map[string]interface{}{}
	if existing, ok := raw["meta_fields"].(map[string]interface{}); ok {
		for key, value := range existing {
			metaFields[key] = value
		}
	}
	metaFields["tags"] = append([]string(nil), tags...)
	out["meta_fields"] = metaFields
	return out
}

func vendorMetaDataFilter(req knowledgeQueryRequest) map[string]any {
	conditions := make([]map[string]any, 0, len(req.MetadataFilter)+len(req.Tags))
	for key, value := range req.MetadataFilter {
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if key == "" || value == "" {
			continue
		}
		conditions = append(conditions, map[string]any{
			"key":   key,
			"op":    "=",
			"value": value,
		})
	}
	for _, tag := range req.Tags {
		tag = strings.TrimSpace(tag)
		if tag == "" {
			continue
		}
		conditions = append(conditions, map[string]any{
			"key":   "tags",
			"op":    "contains",
			"value": tag,
		})
	}
	if len(conditions) == 0 {
		return nil
	}
	return map[string]any{
		"method": "manual",
		"manual": conditions,
		"logic":  "and",
	}
}

func mapDocumentStatus(raw map[string]interface{}) service.DocumentStatus {
	run := strings.ToUpper(strings.TrimSpace(stringField(raw, "run")))
	switch run {
	case "DONE":
		return service.DocumentStatusReady
	case "FAIL":
		return service.DocumentStatusFailed
	case "CANCEL":
		return service.DocumentStatusFailed
	case "RUNNING":
		return service.DocumentStatusParsing
	case "SCHEDULE":
		return service.DocumentStatusUploaded
	default:
		if progress := floatField(raw, "progress"); progress > 0 && progress < 1 {
			return service.DocumentStatusEmbedding
		}
		return service.DocumentStatusUploaded
	}
}

func normalizePage(page, pageSize int) (service.PageInput, error) {
	if page == 0 {
		page = 1
	}
	if pageSize == 0 {
		pageSize = 20
	}
	fields := map[string]string{}
	if page < 1 {
		fields["page"] = "must be greater than or equal to 1"
	}
	if pageSize < 1 || pageSize > 100 {
		fields["pageSize"] = "must be between 1 and 100"
	}
	if len(fields) > 0 {
		return service.PageInput{}, service.ValidationError("request validation failed", fields)
	}
	return service.PageInput{Page: page, PageSize: pageSize}, nil
}

func stringField(raw map[string]interface{}, keys ...string) string {
	for _, key := range keys {
		if value, ok := raw[key]; ok && value != nil {
			switch typed := value.(type) {
			case string:
				return strings.TrimSpace(typed)
			default:
				return strings.TrimSpace(fmt.Sprint(typed))
			}
		}
	}
	return ""
}

func optionalStringField(raw map[string]interface{}, keys ...string) *string {
	value := stringField(raw, keys...)
	if value == "" {
		return nil
	}
	return &value
}

func int64Field(raw map[string]interface{}, keys ...string) int64 {
	for _, key := range keys {
		if value, ok := raw[key]; ok && value != nil {
			switch typed := value.(type) {
			case float64:
				return int64(typed)
			case int64:
				return typed
			case int:
				return int64(typed)
			case json.Number:
				parsed, _ := typed.Int64()
				return parsed
			}
		}
	}
	return 0
}

func optionalInt64Field(raw map[string]interface{}, keys ...string) *int64 {
	value := int64Field(raw, keys...)
	if value == 0 {
		return nil
	}
	return &value
}

func intField(raw map[string]interface{}, keys ...string) int {
	return int(int64Field(raw, keys...))
}

func optionalIntField(raw map[string]interface{}, keys ...string) *int {
	for _, key := range keys {
		value, ok := raw[key]
		if !ok || value == nil {
			continue
		}
		switch typed := value.(type) {
		case float64:
			parsed := int(typed)
			return &parsed
		case int64:
			parsed := int(typed)
			return &parsed
		case int:
			return &typed
		case json.Number:
			if parsed, err := typed.Int64(); err == nil {
				value := int(parsed)
				return &value
			}
		case string:
			if parsed, err := strconv.Atoi(strings.TrimSpace(typed)); err == nil {
				return &parsed
			}
		}
	}
	return nil
}

func embeddingProviderField(raw map[string]interface{}) *string {
	value := stringField(raw, "embedding_provider", "embeddingProvider", "embedding_model", "embeddingModel", "embd_id")
	if value == "" {
		return nil
	}
	parts := strings.Split(value, "@")
	if len(parts) > 1 {
		value = strings.TrimSpace(parts[len(parts)-1])
	}
	if value == "" {
		return nil
	}
	return &value
}

func isRuntimeVectorField(key string) bool {
	return strings.HasPrefix(key, "q_") && strings.HasSuffix(key, "_vec")
}

func floatField(raw map[string]interface{}, keys ...string) float64 {
	for _, key := range keys {
		if value, ok := raw[key]; ok && value != nil {
			switch typed := value.(type) {
			case float64:
				return typed
			case int:
				return float64(typed)
			case int64:
				return float64(typed)
			case json.Number:
				parsed, _ := typed.Float64()
				return parsed
			case string:
				parsed, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
				if err == nil {
					return parsed
				}
			}
		}
	}
	return 0
}

func timeField(raw map[string]interface{}, keys ...string) time.Time {
	for _, key := range keys {
		value, ok := raw[key]
		if !ok || value == nil {
			continue
		}
		switch typed := value.(type) {
		case float64:
			return unixMillisToTime(int64(typed))
		case int64:
			return unixMillisToTime(typed)
		case int:
			return unixMillisToTime(int64(typed))
		case string:
			trimmed := strings.TrimSpace(typed)
			if trimmed == "" {
				continue
			}
			for _, layout := range []string{time.RFC3339Nano, time.RFC3339, "2006-01-02 15:04:05"} {
				if parsed, err := time.Parse(layout, trimmed); err == nil {
					return parsed.UTC()
				}
			}
		}
	}
	return time.Time{}.UTC()
}

func unixMillisToTime(value int64) time.Time {
	if value <= 0 {
		return time.Time{}.UTC()
	}
	if value > 1_000_000_000_000 {
		return time.UnixMilli(value).UTC()
	}
	return time.Unix(value, 0).UTC()
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func newQueryID() string {
	return fmt.Sprintf("kq_%d", time.Now().UTC().UnixNano())
}
