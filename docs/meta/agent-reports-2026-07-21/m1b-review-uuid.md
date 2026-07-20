# m1b-review-uuid 구현 보고서

- 브랜치: `m1b/review-uuid`
- 기준 커밋: `3e80db7`
- 구현 커밋:
  - `0218aa7 feat(review): add UUID-owned canonical artifact layout`
  - `c39f089 feat(review): wire UUID-owned packet review runs`
  - `9252bba fix(review): enforce legacy adapter binding refusals`
- push: 수행하지 않음

## 1. 구현 요약과 파일 목록

ADR-0009의 canonical review artifact 경계를 `waystone/features/review_layout.py`에
구현했다. RFC 9562 UUIDv7 생성/검사, 다섯 artifact kind의 canonical 주소, payload
`run_id` 기록, directory segment와 payload의 이중 검증, add-only publication,
feedback의 명시적 replacement, owner/leaf symlink 거부, typed identity/publication
conflict, 그리고 별도 flat legacy adapter를 포함한다. 신규 의존성은 추가하지 않았다.

Packet-mode `review prepare`는 round-id와 별개의 UUIDv7 owner를 조폐하고
`docs/reviews/runs/<uuid>/request.md` 및 `request.binding.json`에 발행한다. ingest,
pending, remote verify, overlay rule 판독과 round reclose 경로는 canonical evidence와
역사 flat evidence를 명시적으로 구분한다. Canonical 검증 실패나 canonical/flat의 동일
round claim은 flat fallback 없이 거부하고, 역사 flat packet evidence는 현재 설정 mode와
무관하게 read-only로 유지한다.

변경 파일:

- `waystone/features/review_layout.py` — 신규 canonical writer/reader와 legacy adapter
- `scripts/review.py` — packet prepare/ingest/pending/remote/triage 경로 wiring
- `scripts/overlay.py` — canonical feedback를 포함한 Rule 2 판독
- `scripts/round.py` — canonical binding을 인식하는 reclose 경로
- `scripts/tests/test_review_runs_layout.py` — 신규 ADR-0009/PC-14/JW-GPT-015 계약 테스트
- `scripts/tests/test_review_protocol.py` — packet publication fixture를 canonical layout으로 전환
- `scripts/tests/test_review_settlement.py` — ingest/pending fixture를 canonical layout으로 전환
- `scripts/tests/test_improve.py` — 신규 flat writer를 전제하지 않도록 역사 fixture 생성 경계 수정
- `scripts/tests/run_tests.py` — 신규 테스트 모듈 aggregate 등록만 추가

## 2. 계약 매핑

| 계약 / fixture | 이를 단언하는 테스트 함수 |
|---|---|
| ADR-0005: canonical lowercase UUIDv7, version/variant, 74 CSPRNG bits | `ReviewRunsLayoutTests.test_uuid7_generator_uses_canonical_rfc9562_shape` |
| ADR-0009: 다섯 canonical 주소와 writer의 payload `run_id` 기록 | `ReviewRunsLayoutTests.test_writer_maps_all_five_artifact_kinds_and_records_owner` |
| ADR-0009: 발행→reader 귀속→byte-exact round trip | `ReviewRunsLayoutTests.test_writer_round_trip_preserves_published_bytes` |
| ADR-0009: segment 유효+payload 불일치 거부, payload 부재 거부, 일치 귀속 | `ReviewRunsLayoutTests.test_canonical_reader_requires_segment_and_payload_identity` |
| ADR-0009: `runs/` 검사 실패 artifact의 flat fallback 금지 | `ReviewRunsLayoutTests.test_canonical_identity_failure_never_falls_back_to_flat`; `ReviewRunsLayoutTests.test_round_resolver_refuses_matching_rejected_owner_without_flat_fallback`; `ReviewRunsLayoutTests.test_every_canonical_binding_claim_blocks_same_round_flat_fallback` |
| ADR-0009: canonical/flat 동일 round claim 및 symlink identity ambiguity 거부 | `ReviewRunsLayoutTests.test_canonical_and_flat_same_round_is_an_identity_conflict`; `ReviewRunsLayoutTests.test_canonical_reader_and_writer_reject_owner_directory_symlink`; `ReviewRunsLayoutTests.test_broken_canonical_binding_symlink_is_a_recorded_rejection`; `ReviewRunsLayoutTests.test_broken_canonical_fixed_leaf_symlink_is_an_identity_conflict` |
| ADR-0009: malformed foreign owner 격리 | `ReviewRunsLayoutTests.test_foreign_rejected_binding_is_isolated_from_healthy_rounds`; `ReviewRunsLayoutTests.test_rejected_foreign_binding_cannot_override_proven_healthy_owner` |
| ADR-0009: corrupt 기존 feedback identity를 replacement로 은폐하지 않음 | `ReviewRunsLayoutTests.test_feedback_replace_refuses_corrupt_existing_identity` |
| owner 조폐 시점: packet `review prepare`, round-id 재사용 금지, flat 신규 발행 금지 | `ReviewRunsLayoutTests.test_live_packet_prepare_mints_uuid_owner_and_writes_no_flat_artifacts`; `RoundExposureTests.test_close_records_round_exposure` |
| live canonical ingest/pending/remote/overlay 판독 | `ReviewRunsLayoutTests.test_jw_gpt_015_foreign_malformed_sidecar_does_not_block_live_ingest`; `PendingReviewTests.test_normal_completion_precedes_an_exact_current_settlement`; `ReviewRunsLayoutTests.test_remote_verify_reads_canonical_owner`; `ReviewRunsLayoutTests.test_live_overlay_rule_reads_canonical_feedback` |
| canonical evidence가 없는 packet ingest에서 flat 신규 feedback 금지 | `ReviewRunsLayoutTests.test_ingest_without_request_or_binding_refuses_new_flat_feedback` |
| 별도 legacy adapter 경계 및 symlink alias 거부 | `ReviewRunsLayoutTests.test_legacy_adapter_refuses_symlink_aliases`; `ReviewRunsLayoutTests.test_legacy_binding_symlink_cannot_bypass_adapter_in_live_readers` |
| PC-14: 실제 역사 flat request/binding/feedback/settlement read, 경로·bytes 불변, canonical next-write | `ReviewRunsLayoutTests.test_pc14_historical_flat_evidence_stays_legacy_and_byte_unchanged` |
| PC-14: 역사 flat packet ingest/force/triage read-only, mode 변경으로 우회 불가 | `ReviewRunsLayoutTests.test_pc14_legacy_packet_mutations_are_refused_and_bytes_unchanged`; `PendingReviewTests.test_digestless_legacy_ingest_is_refused_and_preserves_flat_bytes` |
| JW-GPT-015 / `fix/ingest-malformed-foreign-freeze-skip`: 타 owner malformed sidecar가 healthy owner read/ingest를 중단하지 않음 | `ReviewRunsLayoutTests.test_jw_gpt_015_foreign_malformed_sidecar_cannot_block_healthy_owner`; `ReviewRunsLayoutTests.test_jw_gpt_015_foreign_malformed_sidecar_does_not_block_live_ingest` |

## 3. 검증 결과

최종 전체 스위트 명령:

```sh
env -u FORCE_COLOR -u CLICOLOR_FORCE uv run scripts/tests/run_tests.py > /tmp/suite-m1b-review-uuid.log 2>&1; echo "suite rc=$?"
```

- suite rc: `0`
- 결과: `Ran 862 tests in 90.877s`, `OK`
- 로그: `/tmp/suite-m1b-review-uuid.log`
- `git diff --check`: 통과
- 전체 스위트가 생성한 worktree 루트의 `.waystone/lock`과 `.waystone/.gitignore`는
  검증 후 제거했으며, 최종 상태에 `.waystone/`은 없다.

## 4. 계약 해석 및 needs-ruling 후보

1. ADR-0009의 fixed leaf에는 generation sequence 슬롯이 없다. 따라서 같은 owner에 대한
   byte-identical re-prepare는 idempotent success로, 다른 bytes의 re-prepare는
   `ArtifactConflict`로 거부하고 새 round/owner를 요구하는 보수적 해석을 택했다. 기존 packet
   generation sidecar처럼 같은 round를 재발행하는 대안은 canonical 주소 계약과 충돌하므로
   구현하지 않았다.
2. Markdown request/feedback의 payload `run_id` wire grammar는 ADR에 명시되지 않았다.
   첫 줄의 bounded JSON identity marker
   `waystone-review-artifact:v1`을 사용했고, marker 부재·schema 불일치·중복 JSON key를 identity
   conflict로 거부한다. YAML frontmatter나 별도 JSON sidecar를 쓰는 대안은 채택하지 않았다.
3. "legacy evidence"를 역사 증거의 provenance이자 read-only strangler 경계로 해석했다.
   따라서 현재 `.waystone.yml`을 packet에서 PR mode로 바꿔도 기존 flat packet feedback의
   ingest/force/triage는 거부한다. 현재 mode가 역사 artifact의 provenance를 재정의하도록 허용하는
   대안은 PC-14 bytes 불변과 충돌한다고 판단했다.
4. 개별 브리핑은 live wiring을 packet-mode로 한정했다. 다섯 artifact kind writer/reader는 새
   모듈에 구현했지만, 현행 PR-mode freeze/demotion publisher를 canonical owner에 연결하지 않았다.
   ADR의 포괄적인 "신규 artifact는 canonical에만" 문구를 packet 한정 wiring보다 우선할지 main
   ruling이 필요하다.
5. `improve.py`는 브리핑에서 명명한 ingest·pending·remote verify reader가 아니고 refactor plan상
   후속 projection 영역이라 canonical scan으로 전환하지 않았다. 다만 overlay의 live Rule 2
   consumer는 canonical feedback을 읽도록 연결했다.
6. Canonical binding은 reader가 검증한 바로 그 payload를 downstream에 전달하도록 고쳤다.
   Request/feedback의 일부 pending/remote consumer는 검증 후 같은 path의 bytes를 다시 읽으므로,
   적대적인 동시 교체까지 계약 범위로 본다면 open file descriptor 또는 digest-bound read API가
   추가로 필요하다. 현재 writer의 add-only/atomic replace와 symlink 거부 범위에서는 검증된다.
7. `review status`의 전체 packet round count는 per-round disposition 전에 전역 scan을 수행한다.
   한 owner의 canonical/flat conflict가 healthy owner의 status 출력을 중단할 수 있으나, 브리핑의
   명시적 reader 목록에는 status가 없어서 수정하지 않았다. JW-GPT-015의 격리 의미를 status까지
   확대할지 ruling이 필요하다.
8. Filesystem identity, publication, canonical scan, rejected owner attribution과 legacy filename
   grammar는 모두 `review_layout.py`에 두었다. 다만 기존 packet의 generation/digest/settlement
   모델에 canonical artifact를 투영하는 domain glue는 `scripts/review.py`에 남아 legacy diff가
   작지 않다. D3의 "최소 wiring"을 단순 line count가 아니라 기존 consumer 통합에 필요한
   최소 의미 변경으로 해석했다.

## 5. 스코프 밖에서 발견한 문제

- `scripts/improve.py`의 reviews projection은 여전히 direct-child flat history만 열거한다.
  Canonical review projection 편입은 후속 M2+ 범위로 남아 있다.
- PR-mode freeze/demotion의 live canonical publication과 PR-mode에 request/binding이 없는 경우의
  신규 flat feedback 생성은 이번 packet-mode wiring 범위 밖이라 그대로다. ADR-0009를 모든 live
  PR publication에 즉시 적용한다면 별도 migration task가 필요하다.
- `review status`는 위 4-7 항목처럼 malformed/conflicting owner의 per-owner 격리를 완전히
  보존하지 않는다.
- aggregate test runner가 worktree 루트에 `.waystone/` lock 상태를 만드는 기존 side effect가
  있다. 이번 검증 뒤 제거했으며 runner 자체는 수정하지 않았다.

## 6. Legacy test-ID 변경 전수 (main 승인 대상)

기준 `3e80db7` 대비 신규 `test_review_runs_layout.py`와 aggregate 등록은 제외했다.
AST 기준 총계는 추가 8, 삭제 8, 변경 48이다.

### 추가 8

- `PacketPublicationTests.test_delayed_echo_remains_bound_after_canonical_reprepare_refusal`
- `PacketPublicationTests.test_missing_or_replaced_canonical_generation_is_unknown_not_receipt_corrupt`
- `PacketPublicationTests.test_narrative_only_reprepare_refuses_fixed_canonical_leaf`
- `PacketPublicationTests.test_render_only_reprepare_refuses_fixed_canonical_leaf`
- `PacketPublicationTests.test_reprepare_conflict_leaves_canonical_projections_byte_exact`
- `IngestTests.test_round_inferred_from_legacy_request_refuses_flat_feedback_write`
- `IngestTests.test_target_mismatch_and_legacy_packet_write_is_refused`
- `PendingReviewTests.test_digestless_legacy_ingest_is_refused_and_preserves_flat_bytes`

### 삭제 8

- `PacketPublicationTests.test_delayed_echo_stamps_named_generation_and_stays_pending_after_reprepare`
- `PacketPublicationTests.test_missing_or_corrupt_named_generation_is_unknown_not_receipt_corrupt`
- `PacketPublicationTests.test_narrative_only_reprepare_reissues_binding_and_reopens_pending`
- `PacketPublicationTests.test_render_only_reprepare_invalidates_old_feedback`
- `PacketPublicationTests.test_reprepare_crash_after_each_projection_write_stays_pending`
- `IngestTests.test_round_inferred_from_request`
- `IngestTests.test_target_mismatch_and_sidecarless_legacy_are_not_configured_feedback`
- `PendingReviewTests.test_digestless_legacy_completion_is_labeled_independently_of_reviewer_coverage`

### 변경 48

`scripts/tests/test_improve.py`:

- `ImproveReviewsTests.test_legacy_label_survives_unconfigured_reviewer_in_real_file_projection`
- `ImproveReviewsTests.test_review_projection_rederives_stale_generation_digest_from_body`
- `ImproveReviewsTests.test_reviews_projection_consumes_rederived_reply_metadata`

`scripts/tests/test_review_protocol.py`:

- `PacketPublicationTests.test_feedback_cache_coverage_edit_cannot_enable_legacy_fallback`
- `PacketPublicationTests.test_feedback_cache_digest_edit_cannot_reassign_verbatim_reply`
- `PacketPublicationTests.test_ingest_rejects_digest_strip_and_v1_downgrade_for_digest_era_round`
- `PacketPublicationTests.test_invalid_stored_round_is_isolated_before_generation_lookup`
- `PacketPublicationTests.test_latest_unpublished_binding_is_the_judged_packet`
- `PacketPublicationTests.test_packet_gate_rejects_post_prepare_narrative_edit`
- `PacketPublicationTests.test_packet_publication_gate_uses_real_remote_and_rejects_partial_commit`
- `PacketPublicationTests.test_pending_exposes_latest_binding_projection_mismatches`
- `PacketPublicationTests.test_prepare_binds_request_to_closeout_head_and_is_idempotent`
- `PacketPublicationTests.test_prepare_rejects_noncanonical_binding_instead_of_reporting_success`
- `PacketPublicationTests.test_prepare_renders_template_from_round_exposure_and_narrative`
- `PacketPublicationTests.test_published_stale_sidecar_cannot_stand_in_for_local_latest`
- `PacketPublicationTests.test_rendered_request_exposes_self_digest_and_canonicalizer_is_header_bounded`
- `PacketPublicationTests.test_round_request_binding_rejects_duplicate_json_fields`
- `PacketPublicationTests.test_stale_echo_recovers_when_its_generation_becomes_latest_again`
- `PacketPublicationTests.test_stamped_feedback_blocks_legacy_fallback_if_latest_digest_is_stripped`
- `PacketPublicationTests.test_symlinked_packet_artifacts_are_rejected`
- `PacketPublicationTests.test_unknown_echo_is_distinct_from_stale_generation`
- `PacketPublicationTests.test_v2_binding_missing_or_invalid_digest_is_corrupt`
- `PacketPublicationTests.test_v2_reply_without_digest_stays_pending_with_resubmission_guidance`
- `RoundExposureTests.test_close_records_round_exposure`
- `RoundExposureTests.test_same_round_reclose_preserves_original_previous_round_diff_base`

`scripts/tests/test_review_settlement.py`:

- `IngestTests.test_byte_exact_copy_and_consume`
- `IngestTests.test_feedback_body_boundary_damage_is_unknown`
- `IngestTests.test_feedback_reader_does_not_load_arbitrary_reply_body`
- `IngestTests.test_feedback_separator_crossing_header_cap_is_accepted`
- `IngestTests.test_force_reingest_replaces_legacy_identity_event_for_round`
- `IngestTests.test_force_reingest_rolls_feedback_back_if_event_correction_fails`
- `IngestTests.test_invalid_utf8_header_ingests_as_absent_without_replacement`
- `IngestTests.test_packet_ingest_does_not_synthesize_missing_sidecar_from_request`
- `IngestTests.test_pre_echo_receipt_without_verbatim_envelope_is_not_promoted`
- `IngestTests.test_projection_recomputes_binding_and_rejects_feedback_round_mismatch`
- `IngestTests.test_projection_rejects_stored_metadata_that_disagrees_with_body`
- `IngestTests.test_reingest_requires_force_and_preserves_source_on_refusal`
- `IngestTests.test_stored_metadata_reader_projects_verbatim_body_header_only`
- `IngestTests.test_triage_command_refuses_missing_or_damaged_markers`
- `IngestTests.test_triage_command_replaces_only_marked_tail_with_quoted_markers_in_reply`
- `IngestTests.test_triage_refuses_masked_canonical_marker_via_offset_anchor`
- `IngestTests.test_warn_failure_is_noticed_without_changing_ingest_exit`
- `IngestTests.test_ws_finding_blocks_build_triage_skeleton`
- `PendingReviewTests.test_canonical_reingest_supersedes_stale_settlement`
- `PendingReviewTests.test_corrupt_latest_binding_keeps_old_matching_feedback_pending_unknown`
- `PendingReviewTests.test_latest_binding_controls_pending_and_old_packet_feedback_cannot_silence_it`
- `PendingReviewTests.test_normal_completion_precedes_an_exact_current_settlement`
- `PendingReviewTests.test_reply_matching_latest_target_completes_even_from_unconfigured_model`
