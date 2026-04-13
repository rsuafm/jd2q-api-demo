# JD-to-Query MVP Contracts (Scaffold Step)

## 1) Request Input Schema

`GenerateRequest`
- `jd_id: str`
- `j2q_model: str`
- `sections: list[SectionInput]`
- `taxonomy_retrieval_json_path: str`
- `tool_master_json_path: str`

`SectionInput`
- `section_name: str`
- `text: str`

## 2) Layer Schemas

### Sentence Split
Input: `GenerateRequest`  
Output: `SentenceSplitOutput`
- `jd_id: str`
- `j2q_model: str`
- `sentence_units: list[SentenceUnit]`

`SentenceUnit`
- `sentence_id: int`
- `sentence: str`
- `section: str`
- `normalized_text: str`

### Top1 Match
Input: `SentenceSplitOutput` + `list[TaxonomyRetrievalRow]` + `list[ToolMasterRow]`  
Output: `SentenceTop1MatchOutput`
- `jd_id: str`
- `j2q_model: str`
- `sentence_top1_matches: list[SentenceTop1Match]`

`SentenceTop1Match`
- `sentence_id: int`
- `section: str`
- `taxonomy_row_no: int | null`

Top1 candidate filtering behavior:
- If a sentence contains any tool term (`tool_master.tool_groups[].terms`, case-insensitive substring match on `sentence.normalized_text`), collect matched `tool_code`s.
- If matched `tool_code`s exist, candidate taxonomy rows for that sentence are restricted to `tool_master` rows whose `tool_groups` contain at least one matched `tool_code`.
- If no tool term match exists, candidate taxonomy rows for that sentence are the full retrieval taxonomy.
- Gemini selects one `taxonomy_row_no` (or `null`) per sentence only from that sentence's candidate list.

### Task-to-Tool Expansion
Input: `SentenceTop1MatchOutput` + `list[ToolMasterRow]`  
Output: `SentenceToolExpansionOutput`
- `jd_id: str`
- `j2q_model: str`
- `sentence_tool_expansions: list[SentenceToolExpansion]`

`SentenceToolExpansion`
- `sentence_id: int`
- `section: str`
- `taxonomy_row_no: int | null`
- `tool_groups: list[ToolGroup]`

`ToolGroup`
- `tool_code: str`
- `category: str`
- `terms_operator: "OR"`
- `terms: list[str]`

### Global Boolean AST
Input: `SentenceToolExpansionOutput`  
Output: `GlobalBooleanAstOutput`
- `jd_id: str`
- `j2q_model: str`
- `global_boolean_ast: AstGlobalGroupNode`
- `unresolved_sentence_ids: list[int]`

`AstGlobalGroupNode`
- `type: "group"`
- `level: "global"`
- `operator: "AND"`
- `children: list[AstSectionGroupNode]`

`AstSectionGroupNode`
- `type: "group"`
- `level: "section"`
- `section: str` (e.g., `"must"`, `"nice"`)
- `operator: "AND" | "OR"` (`must=AND`, `nice=OR`)
- `children: list[AstSentenceGroupNode]`

`AstSentenceGroupNode`
- `type: "group"`
- `level: "sentence"`
- `sentence_id: int`
- `operator: "AND"`
- `children: list[AstTermGroupNode]`

`AstTermGroupNode`
- `type: "term_group"`
- `tool_code: str`
- `category: str`
- `terms_operator: "OR"`
- `terms: list[str]`

### Compile
Input: `GlobalBooleanAstOutput` + `SentenceSplitOutput` + `SentenceTop1MatchOutput` + `list[TaxonomyRetrievalRow]`  
Output: `CompileOutput`
- `jd_id: str`
- `j2q_model: str`
- `sql_where_clause: str`
- `sentence_taxonomy_pairs: list[SentenceTaxonomyPair]`
- `clause_trace: list[ClauseTraceItem]`
- `unresolved_sentence_ids: list[int]`

`SentenceTaxonomyPair`
- `sentence_id: int`
- `sentence: str`
- `section: str`
- `taxonomy_row_no: int | null`
- `task_doc: str | null`

`ClauseTraceItem`
- `section: str`
- `sentence_id: int`
- `sentence: str`
- `taxonomy_row_no: int | null`
- `task_doc: str | null`
- `tool_code: str`
- `terms_operator: str`
- `terms: list[str]`

## 3) Query Logic Rules
- Terms inside one tool group are combined with `OR`.
- Multiple tool codes inside one sentence are combined with `AND`.
- Sentence groups where `section == "must"` are combined with `AND`.
- Sentence groups where `section == "nice"` are combined with `OR`.
- Section blocks (`must`, `nice`, etc.) are combined with `AND`.

## 4) Scaffold-Step Behavior
- Current scaffold may return placeholder SQL (`"1=1"`).
- `clause_trace` may be an empty list.
- Layer functions are schema-valid stubs with deterministic placeholder behavior.
