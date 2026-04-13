from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SectionInput(BaseModel):
    section_name: str
    text: str


class GenerateRequest(BaseModel):
    jd_id: str
    j2q_model: str
    sections: list[SectionInput]
    taxonomy_retrieval_json_path: str
    tool_master_json_path: str


class SentenceUnit(BaseModel):
    sentence_id: int
    sentence: str
    section: str
    normalized_text: str


class SentenceSplitOutput(BaseModel):
    jd_id: str
    j2q_model: str
    sentence_units: list[SentenceUnit]


class SentenceTop1Match(BaseModel):
    sentence_id: int
    section: str
    taxonomy_row_no: int | None


class SentenceTop1MatchOutput(BaseModel):
    jd_id: str
    j2q_model: str
    sentence_top1_matches: list[SentenceTop1Match]


class ToolGroup(BaseModel):
    tool_code: str
    category: str
    terms_operator: Literal["OR"] = "OR"
    terms: list[str]


class SentenceToolExpansion(BaseModel):
    sentence_id: int
    section: str
    taxonomy_row_no: int | None
    tool_groups: list[ToolGroup]


class SentenceToolExpansionOutput(BaseModel):
    jd_id: str
    j2q_model: str
    sentence_tool_expansions: list[SentenceToolExpansion]


class AstTermGroupNode(BaseModel):
    type: Literal["term_group"] = "term_group"
    tool_code: str
    category: str
    terms_operator: Literal["OR"]
    terms: list[str]


class AstSentenceGroupNode(BaseModel):
    type: Literal["group"] = "group"
    level: Literal["sentence"] = "sentence"
    sentence_id: int
    operator: Literal["AND"] = "AND"
    children: list[AstTermGroupNode] = Field(default_factory=list)


class AstSectionGroupNode(BaseModel):
    type: Literal["group"] = "group"
    level: Literal["section"] = "section"
    section: str
    operator: Literal["AND", "OR"]
    children: list[AstSentenceGroupNode] = Field(default_factory=list)


class AstGlobalGroupNode(BaseModel):
    type: Literal["group"] = "group"
    level: Literal["global"] = "global"
    operator: Literal["AND"] = "AND"
    children: list[AstSectionGroupNode] = Field(default_factory=list)


class GlobalBooleanAstOutput(BaseModel):
    jd_id: str
    j2q_model: str
    global_boolean_ast: AstGlobalGroupNode
    unresolved_sentence_ids: list[int]


class SentenceTaxonomyPair(BaseModel):
    sentence_id: int
    sentence: str
    section: str
    taxonomy_row_no: int | None
    task_doc: str | None


class ClauseTraceItem(BaseModel):
    section: str
    sentence_id: int
    sentence: str
    taxonomy_row_no: int | None
    task_doc: str | None
    tool_code: str
    terms_operator: str
    terms: list[str]


class CompileOutput(BaseModel):
    jd_id: str
    j2q_model: str
    sql_where_clause: str
    sentence_taxonomy_pairs: list[SentenceTaxonomyPair]
    clause_trace: list[ClauseTraceItem]
    unresolved_sentence_ids: list[int]


class TaxonomyRetrievalRow(BaseModel):
    No: int
    task_doc: str


class ToolMasterRow(BaseModel):
    No: int
    task_doc: str
    tool_groups: list[ToolGroup]
