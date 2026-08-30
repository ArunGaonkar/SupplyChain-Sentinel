# Segments

Only `pharma.yaml` is implemented in this build. `textile.yaml` and
`semiconductor.yaml` are intentionally **not** included — the loader
(`src/config.py`) takes a `--segment` argument so adding one is just
adding a new YAML file with the same shape (countries / companies /
commodities / policy_types / query terms). See the README's "Out of
scope" section for why these weren't built this round.
