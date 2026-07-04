package adapter

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Sakayori-Iroha-168/Software_Teamwork/services/knowledge/internal/adapterconfig"
	"github.com/Sakayori-Iroha-168/Software_Teamwork/services/knowledge/internal/service"
)

func TestHealthz(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("pong"))
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: vendor.URL,
		ServiceToken:     testServiceToken,
	}, nil)

	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}

	var payload map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	data, ok := payload["data"].(map[string]any)
	if !ok {
		t.Fatalf("data=%v", payload["data"])
	}
	if data["service"] != "knowledge-adapter" {
		t.Fatalf("service=%v", data["service"])
	}
}

func TestReadyzVendorUnavailable(t *testing.T) {
	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: "http://127.0.0.1:1",
		ServiceToken:     testServiceToken,
	}, nil)

	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestReadyzSanitizesRuntimeStatusErrors(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/system/ping":
			_, _ = w.Write([]byte("pong"))
		case "/api/v1/system/status":
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte(`<html>debug config VENDOR_RUNTIME_SERVICE_TOKEN=secret-token</html>`))
		default:
			t.Fatalf("unexpected vendor path %s", r.URL.Path)
		}
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:     "test",
		VendorRuntimeURL:   vendor.URL,
		ServiceToken:       testServiceToken,
		VendorRuntimeToken: "runtime-token",
	}, nil)

	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	body := rec.Body.String()
	for _, leaked := range []string{"secret-token", "<html>", vendor.URL, "internal_error", "status_url"} {
		if strings.Contains(body, leaked) {
			t.Fatalf("readyz leaked %q in body: %s", leaked, body)
		}
	}
	if !strings.Contains(body, "vendor runtime status unavailable") {
		t.Fatalf("readyz body does not include sanitized dependency error: %s", body)
	}

	req := httptest.NewRequest(http.MethodGet, "/internal/v1/runtime/status", nil)
	req.Header.Set("X-Service-Token", testServiceToken)
	rec = httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("runtime status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "internal_error") {
		t.Fatalf("internal runtime status did not include diagnostic error: %s", rec.Body.String())
	}
}

func TestReadyzRequiresRuntimeTaskExecutorHeartbeat(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/system/ping":
			_, _ = w.Write([]byte("pong"))
		case "/api/v1/system/status":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"code":0,"data":{"doc_engine":{"status":"green"},"storage":{"status":"green"},"database":{"status":"green"},"redis":{"status":"green"},"task_executor_heartbeats":{}}}`))
		default:
			t.Fatalf("unexpected vendor path %s", r.URL.Path)
		}
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:     "test",
		VendorRuntimeURL:   vendor.URL,
		ServiceToken:       testServiceToken,
		VendorRuntimeToken: "runtime-token",
	}, nil)

	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "task_executor_ready") || !strings.Contains(rec.Body.String(), "run-local.sh") {
		t.Fatalf("readyz body does not include task executor diagnostic: %s", rec.Body.String())
	}
}

func TestReadyzQueryModeAllowsMissingRuntimeTaskExecutorHeartbeat(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/system/ping":
			_, _ = w.Write([]byte("pong"))
		case "/api/v1/system/status":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"code":0,"data":{"doc_engine":{"status":"green"},"storage":{"status":"green"},"database":{"status":"green"},"redis":{"status":"green"},"task_executor_heartbeats":{}}}`))
		default:
			t.Fatalf("unexpected vendor path %s", r.URL.Path)
		}
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:       "test",
		VendorRuntimeURL:     vendor.URL,
		ServiceToken:         testServiceToken,
		VendorRuntimeToken:   "runtime-token",
		RuntimeReadinessMode: adapterconfig.RuntimeReadinessModeQuery,
	}, nil)

	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	body := rec.Body.String()
	for _, expected := range []string{`"runtime_readiness_mode":"query"`, `"task_executor_ready":false`, `"task_executor_count":0`} {
		if !strings.Contains(body, expected) {
			t.Fatalf("readyz body missing %s: %s", expected, body)
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/internal/v1/runtime/status", nil)
	req.Header.Set("X-Service-Token", testServiceToken)
	rec = httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("runtime status=%d body=%s", rec.Code, rec.Body.String())
	}
	body = rec.Body.String()
	for _, expected := range []string{`"runtime_readiness_mode":"query"`, `"task_executor_ready":false`, `"task_executor_count":0`} {
		if !strings.Contains(body, expected) {
			t.Fatalf("runtime status body missing %s: %s", expected, body)
		}
	}
}

func TestReadyzAcceptsRuntimeTaskExecutorHeartbeat(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/system/ping":
			_, _ = w.Write([]byte("pong"))
		case "/api/v1/system/status":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(fmt.Sprintf(`{"code":0,"data":{"doc_engine":{"status":"green"},"storage":{"status":"green"},"database":{"status":"green"},"redis":{"status":"green"},"task_executor_heartbeats":{"task_executor_common_1":[{"now":%q}]}}}`, time.Now().Format(time.RFC3339Nano))))
		default:
			t.Fatalf("unexpected vendor path %s", r.URL.Path)
		}
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:     "test",
		VendorRuntimeURL:   vendor.URL,
		ServiceToken:       testServiceToken,
		VendorRuntimeToken: "runtime-token",
	}, nil)

	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"task_executor_ready":true`) {
		t.Fatalf("readyz body does not include ready task executor: %s", rec.Body.String())
	}
}

func TestRuntimeTaskExecutorReadyRejectsStaleHeartbeat(t *testing.T) {
	_, ready := runtimeTaskExecutorReady(map[string]interface{}{
		"task_executor_common_1": []interface{}{
			map[string]interface{}{"now": time.Now().Add(-10 * time.Minute).Format(time.RFC3339Nano)},
		},
	})
	if ready {
		t.Fatal("stale task executor heartbeat was treated as ready")
	}
}

func TestListKnowledgeBasesRequiresAuth(t *testing.T) {
	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: "http://127.0.0.1:1",
		ServiceToken:     testServiceToken,
	}, nil)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/internal/v1/knowledge-bases", nil)
	req.Header.Set("X-Service-Token", testServiceToken)
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestInternalRoutesRequireServiceToken(t *testing.T) {
	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: "http://127.0.0.1:1",
		ServiceToken:     testServiceToken,
	}, nil)

	req := httptest.NewRequest(http.MethodGet, "/internal/v1/knowledge-bases", nil)
	req.Header.Set("X-User-Id", "usr_test")
	req.Header.Set("X-User-Permissions", "knowledge:read")
	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("missing token status=%d body=%s", rec.Code, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodGet, "/internal/v1/knowledge-bases", nil)
	req.Header.Set("X-Service-Token", "wrong-token")
	req.Header.Set("X-User-Id", "usr_test")
	req.Header.Set("X-User-Permissions", "knowledge:read")
	rec = httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("wrong token status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestListKnowledgeBasesMapsVendorResponse(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/datasets" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		if got := r.Header.Get("X-User-Id"); got != "" {
			t.Fatalf("X-User-Id=%q, want no forwarded runtime user identity", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"code":0,"data":[{"id":"kb_1","name":"Docs","description":"demo","chunk_method":"naive","document_count":2,"chunk_count":10,"create_time":1700000000000}],"total_datasets":1}`))
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: vendor.URL,
		ServiceToken:     testServiceToken,
	}, nil)

	req := httptest.NewRequest(http.MethodGet, "/internal/v1/knowledge-bases", nil)
	req.Header.Set("X-User-Id", "usr_test")
	req.Header.Set("X-Service-Token", testServiceToken)
	req.Header.Set("X-User-Permissions", "knowledge:read")
	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}

	var payload struct {
		Data []map[string]any `json:"data"`
		Page struct {
			Total int64 `json:"total"`
		} `json:"page"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(payload.Data) != 1 || payload.Data[0]["id"] != "kb_1" {
		t.Fatalf("data=%v", payload.Data)
	}
	if payload.Page.Total != 1 {
		t.Fatalf("total=%d", payload.Page.Total)
	}
}

func TestListKnowledgeBasesMapsVendorUnauthorizedAsDependencyError(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/datasets" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"code":401,"message":"runtime token rejected"}`))
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: vendor.URL,
		ServiceToken:     testServiceToken,
	}, nil)

	req := httptest.NewRequest(http.MethodGet, "/internal/v1/knowledge-bases", nil)
	req.Header.Set("X-User-Id", "usr_test")
	req.Header.Set("X-Service-Token", testServiceToken)
	req.Header.Set("X-User-Permissions", "knowledge:read")
	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}

	var payload struct {
		Error struct {
			Code string `json:"code"`
		} `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if payload.Error.Code != "dependency_error" {
		t.Fatalf("error code=%q body=%s", payload.Error.Code, rec.Body.String())
	}
}

func TestCreateKnowledgeQueryMapsRetrieval(t *testing.T) {
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/datasets/search" || r.Method != http.MethodPost {
			t.Fatalf("method=%s path=%s", r.Method, r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"code":0,"message":"success","data":{"total":1,"chunks":[{"id":"chunk_1","doc_id":"doc_1","kb_id":"kb_1","similarity":0.91,"docnm_kwd":"readme.md","content_with_weight":"hello world","section_path_kwd":"ASTM D445-2015 > 1 Scope","doc_type_kwd":"clause"}]}}`))
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: vendor.URL,
		ServiceToken:     testServiceToken,
	}, nil)

	req := httptest.NewRequest(http.MethodPost, "/internal/v1/knowledge-queries", strings.NewReader(`{"query":"hello","knowledgeBaseIds":["kb_1"]}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-User-Id", "usr_test")
	req.Header.Set("X-Service-Token", testServiceToken)
	req.Header.Set("X-User-Permissions", "knowledge:read")
	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}

	var payload struct {
		Data struct {
			Results []map[string]any `json:"results"`
			Trace   struct {
				EmbeddingModel     string `json:"embeddingModel"`
				EmbeddingDimension int    `json:"embeddingDimension"`
			} `json:"trace"`
		} `json:"data"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(payload.Data.Results) != 1 {
		t.Fatalf("results=%v", payload.Data.Results)
	}
	if payload.Data.Results[0]["chunkId"] != "chunk_1" {
		t.Fatalf("chunk=%v", payload.Data.Results[0])
	}
	if payload.Data.Results[0]["sectionPath"] != "ASTM D445-2015 > 1 Scope" {
		t.Fatalf("sectionPath not mapped: %v", payload.Data.Results[0])
	}
	if payload.Data.Results[0]["chunkType"] != "clause" {
		t.Fatalf("chunkType not mapped: %v", payload.Data.Results[0])
	}
	if payload.Data.Trace.EmbeddingModel == "vendor-default" || payload.Data.Trace.EmbeddingDimension == 0 {
		t.Fatalf("trace should not contain fake runtime facts: %+v", payload.Data.Trace)
	}
}

func TestCreateKnowledgeQueryExpandsEmptyKnowledgeBasesAcrossEmbeddingGroups(t *testing.T) {
	type searchCall struct {
		ids []string
	}
	var calls []searchCall
	vendor := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/datasets/search" || r.Method != http.MethodPost {
			t.Fatalf("method=%s path=%s", r.Method, r.URL.Path)
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode search body: %v", err)
		}
		ids := stringSliceFromAny(body["dataset_ids"])
		calls = append(calls, searchCall{ids: ids})
		score := 0.82
		if len(ids) > 0 && ids[0] == "kb_b" {
			score = 0.93
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code": 0,
			"data": map[string]any{
				"total": 1,
				"chunks": []map[string]any{{
					"id": "chunk_" + ids[0], "doc_id": "doc_1",
					"kb_id": ids[0], "similarity": score, "docnm_kwd": "manual.pdf",
					"content_with_weight": "runtime scope result",
				}},
			},
		})
	}))
	defer vendor.Close()

	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: vendor.URL,
		ServiceToken:     testServiceToken,
	}, nil, WithRuntimeKnowledgeBaseCatalog(queryCatalogStub{items: []service.RuntimeKnowledgeBase{
		{ID: "kb_a", EmbeddingID: "embed_a", ChunkCount: 3},
		{ID: "kb_b", EmbeddingID: "embed_b", ChunkCount: 5},
		{ID: "kb_empty", EmbeddingID: "embed_a", ChunkCount: 0},
	}}))

	req := httptest.NewRequest(http.MethodPost, "/internal/v1/knowledge-queries", strings.NewReader(`{"query":"transformer","topK":2}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-User-Id", "usr_test")
	req.Header.Set("X-Service-Token", testServiceToken)
	req.Header.Set("X-User-Permissions", "knowledge:read")
	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if len(calls) != 2 {
		t.Fatalf("search calls=%+v, want two embedding groups", calls)
	}
	if len(calls[0].ids) != 1 || calls[0].ids[0] != "kb_a" {
		t.Fatalf("first call=%+v", calls[0])
	}
	if len(calls[1].ids) != 1 || calls[1].ids[0] != "kb_b" {
		t.Fatalf("second call=%+v", calls[1])
	}

	var payload struct {
		Data struct {
			Results []struct {
				KnowledgeBaseID string  `json:"knowledgeBaseId"`
				Score           float64 `json:"score"`
			} `json:"results"`
		} `json:"data"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(payload.Data.Results) != 2 || payload.Data.Results[0].KnowledgeBaseID != "kb_b" || payload.Data.Results[0].Score != 0.93 {
		t.Fatalf("results=%+v", payload.Data.Results)
	}
}

func TestNotFoundRoute(t *testing.T) {
	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: "http://127.0.0.1:1",
		ServiceToken:     testServiceToken,
	}, nil)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/internal/v1/unknown", nil)
	req.Header.Set("X-Service-Token", testServiceToken)
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

type queryCatalogStub struct {
	items []service.RuntimeKnowledgeBase
}

func (s queryCatalogStub) ListRuntimeKnowledgeBases(_ context.Context, ids []string) ([]service.RuntimeKnowledgeBase, error) {
	if len(ids) == 0 {
		return append([]service.RuntimeKnowledgeBase(nil), s.items...), nil
	}
	wanted := map[string]struct{}{}
	for _, id := range ids {
		wanted[id] = struct{}{}
	}
	items := []service.RuntimeKnowledgeBase{}
	for _, item := range s.items {
		if _, ok := wanted[item.ID]; ok {
			items = append(items, item)
		}
	}
	return items, nil
}

func stringSliceFromAny(value any) []string {
	raw, _ := value.([]any)
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		if text, ok := item.(string); ok {
			out = append(out, text)
		}
	}
	return out
}

func TestListParserConfigsRequiresDatabase(t *testing.T) {
	server := NewServer(adapterconfig.Config{
		ServiceVersion:   "test",
		VendorRuntimeURL: "http://127.0.0.1:1",
		ServiceToken:     testServiceToken,
	}, nil)

	req := httptest.NewRequest(http.MethodGet, "/internal/v1/parser-configs", nil)
	req.Header.Set("X-User-Id", "usr_admin")
	req.Header.Set("X-Service-Token", testServiceToken)
	req.Header.Set("X-User-Permissions", "knowledge:admin")
	rec := httptest.NewRecorder()
	server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}
