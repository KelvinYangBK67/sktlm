DATE=2026-09-25
BRANCH=exp/s1m2-reusable-pieces
STATUS=S1M2_V3_FOUR_VM_PRE_VM_CONTROL_PLANE_READY

SCIENTIFIC_SEMANTICS=FROZEN
RUNTIME_IMPLEMENTATION=FROZEN
CONTROL_PLANE_REOPENED_FOR_PRE_VM_COMPATIBILITY=YES

FULL_SIX_CELL_SCIENTIFIC_MATRIX != CURRENT_ACTIVE_VM_DEPLOYMENT

CURRENT_ACTIVE_VM_SET=core-07,core-08,core-09,core-10
CURRENT_ACTIVE_CELL_COUNT=4
CURRENT_EXECUTION_SCOPE=EXPLICIT_SUBSET

ACTIVE_MAPPING:
core-07=s1m2_m0_prime_iast_continuous
core-08=s1m2_m0_devanagari_continuous
core-09=s1m2_m0_iast_surface_word
core-10=s1m2_m0_iast_legacy_joined

ACTIVE_DEPLOYMENT_MANIFEST=configs/deployment/s1m2_v3_active_four_vm.json
DEPLOYMENT_ID=s1m2-v3-active-four-vm-20260925
FINAL_PLAN=artifacts/s1m2_production/final_plan_v3_active4_20260925.json
FULL_WORKERS=12
FULL_M0_AUTHORIZED=NO
FULL_M0_PROCESS_RUNNING=NO

The six-cell production/scientific contract remains byte-identical. The two
active IAST non-continuous bundle plans were rematerialized from stale v1 into
current v2 direct-seek execution metadata with exact input and segment
coverage. All four active plans pass the v2 loader. The deployment manifest is
the authority for current scope, host roles, and bundle identities.

No VM, SSH, cloud operation, Full authorization, training, inference,
scientific workload, benchmark, or profiling run occurred in this repair.

Authority:
reports/core_methods/reusable_pieces/s1m2_v3_pre_vm_control_plane_repair_20260925.md
reports/core_methods/reusable_pieces/evidence/s1m2_v3_pre_vm_control_plane_repair_20260925.json

NEXT_RESEARCHER_ACTION=CONFIRM COST/TIME STOP RULE, THEN CREATE PLAN-SPECIFIC FULL AUTHORIZATION AND POWER ON core-07/core-08/core-09/core-10

Every Full run command must include:
--authorization <artifact>

Do not launch VM/cloud/Full M0 automatically.
