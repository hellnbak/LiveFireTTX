# Scenario Packs

LiveFireTTX v1.3 scenario packs are portable JSON exercise designs. They are
independent from generated exercise instances and do not include exercise IDs,
package paths, trigger state, run events, assessments, improvement actions, or
evidence.

## Contents

A pack contains:

- Schema version, slug, semantic version, name, and description
- One supported built-in base scenario
- Default business system, difficulty, duration, roles, and objectives
- Optional narrative, safe artifact, and allowlisted chaos inject definitions
- Optional objective-linked evaluator checkpoints

Every imported or captured version is immutable and receives a canonical
SHA-256 checksum. Reusing a slug and version with different content is rejected.

## Workflow

1. Open **Design Library**.
2. Create an organization profile if the exercise should reuse organization
   roles, objectives, and system naming.
3. Launch a built-in or imported pack with optional profile context.
4. Tailor the generated exercise and MSEL as needed.
5. In the command center, capture the resulting design with a new semantic
   version.
6. Export the JSON pack and import it into another v1.3 installation.

The import form supports a local file picker without uploading to a separate
storage location; browser JavaScript reads the file into the bounded JSON form.

## Validation and Safety

- Imports are limited to 256 KB, 100 injects, and 50 checkpoints.
- Strings, lists, schedules, durations, stages, objective links, and semantic
  versions are bounded and validated.
- A pack must select an existing built-in base scenario.
- Chaos injects may reference only actions already allowed by that base.
- Imports cannot provide commands, scripts, executable payloads, controller
  addresses, generated package paths, or output paths.
- Artifact references are limited to known generated artifacts or bounded safe
  artifact types whose content is watermarked during generation.
- Exercise generation still passes through the standard target, controller,
  path-containment, preflight, duration, guardrail, and emergency-stop controls.

See [`../examples/scenario-pack-example.json`](../examples/scenario-pack-example.json)
for a complete portable definition.

## Organization Profiles

Organization profiles are separate immutable versions. They contain a business
system, participant roles, and objectives. Applying a profile overrides those
pack defaults while preserving the pack's scenario, difficulty, duration,
inject design, and checkpoints. Profiles can be exported as JSON for review and
record keeping.
