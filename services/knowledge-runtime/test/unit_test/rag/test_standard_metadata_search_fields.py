#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import sys
import types
from importlib import util
from pathlib import Path

import pytest

_fake_query = types.ModuleType("rag.nlp.query")


class _DummyFulltextQueryer:
    pass


_fake_query.FulltextQueryer = _DummyFulltextQueryer
_fake_rag = types.ModuleType("rag")
_fake_rag.__path__ = [str(Path(__file__).resolve().parents[3] / "rag")]
_fake_nlp = types.ModuleType("rag.nlp")
_fake_nlp.__path__ = [str(Path(__file__).resolve().parents[3] / "rag" / "nlp")]
_fake_nlp.query = _fake_query
_fake_nlp.rag_tokenizer = types.SimpleNamespace(fine_grained_tokenize=lambda text: text)

sys.modules["rag"] = _fake_rag
sys.modules["rag.nlp"] = _fake_nlp
sys.modules["rag.nlp.query"] = _fake_query

_fake_settings = types.ModuleType("common.settings")
_fake_settings.DOC_ENGINE_OCEANBASE = False
_fake_settings.DOC_ENGINE_INFINITY = False
sys.modules.setdefault("common.settings", _fake_settings)


def _load_search_module():
    path = Path(__file__).resolve().parents[3] / "rag" / "nlp" / "search.py"
    spec = util.spec_from_file_location("rag.nlp.search", path)
    module = util.module_from_spec(spec)
    sys.modules["rag.nlp.search"] = module
    spec.loader.exec_module(module)
    return module


search_module = _load_search_module()
Dealer = search_module.Dealer
STANDARD_PUBLIC_FIELDS = search_module.STANDARD_PUBLIC_FIELDS


class _FakeDocStore:
    def __init__(self):
        self.searched_fields = []

    def search(self, select_fields, *args, **kwargs):
        self.searched_fields.append(list(select_fields))
        return {"hits": []}

    def get_total(self, _res):
        return 0

    def get_doc_ids(self, _res):
        return []

    def get_highlight(self, _res, _keywords, _field):
        return {}

    def get_aggregation(self, _res, _field):
        return []

    def get_fields(self, _res, _fields):
        return {}


@pytest.mark.asyncio
async def test_search_default_fields_include_standard_public_metadata():
    store = _FakeDocStore()
    dealer = Dealer(store)

    await dealer.search(
        {"question": "", "page": 1, "size": 10},
        "ragflow_runtime",
        ["kb_1"],
        emb_mdl=None,
    )

    assert store.searched_fields, "search was not called"
    selected = set(store.searched_fields[0])
    for field in STANDARD_PUBLIC_FIELDS:
        assert field in selected


def test_runtime_private_field_detection_preserves_standard_titles():
    assert search_module.is_runtime_private_field("content_ltks")
    assert search_module.is_runtime_private_field("title_tks")
    assert search_module.is_runtime_private_field("q_1024_vec")
    assert not search_module.is_runtime_private_field("table_title_tks")
    assert not search_module.is_runtime_private_field("clause_title_tks")
    assert not search_module.is_runtime_private_field("section_path_kwd")


def test_chunk_list_default_fields_include_standard_public_metadata():
    store = _FakeDocStore()
    dealer = Dealer(store)

    dealer.chunk_list("doc_1", "scope_1", ["kb_1"], max_count=1)

    assert store.searched_fields, "search was not called"
    selected = set(store.searched_fields[0])
    for field in STANDARD_PUBLIC_FIELDS:
        assert field in selected


def test_standard_fields_are_not_added_for_oceanbase(monkeypatch):
    monkeypatch.setattr(search_module.settings, "DOC_ENGINE_OCEANBASE", True)
    monkeypatch.setattr(search_module.settings, "DOC_ENGINE_INFINITY", False)

    selected = search_module.with_standard_public_fields(["docnm_kwd"], search_module.standard_public_fields_supported())

    assert selected == ["docnm_kwd"]
