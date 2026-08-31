# One-command demo

`make demo` (or `python -m lakehouse demo`) seeds Bronze, walks Bronze →
Silver → quality → Gold, queries Gold, and **asserts** the path produced
data.

## Commands

```bash
# Live MiniStack path (requires make up && make infra)
make demo
python -m lakehouse demo --mode live --count 20

# In-memory path (no MiniStack; used by unit tests)
python -m lakehouse demo --mode offline --count 20
```

`--mode auto` (CLI default) tries MiniStack and falls back to the
in-memory path when S3/DynamoDB are unreachable.

## Assertions

| Check | Offline | Live |
| --- | --- | --- |
| Seeded events > 0 | yes | yes |
| Silver valid rows > 0 | yes | yes |
| Quality gate passed | yes | yes |
| Gold event count > 0 | yes | yes |
| Gold event count == Silver valid | yes | no (Gold tables accumulate) |

The command exits `1` when any assertion fails and prints the JSON
payload (including `assertions.failures`) on stdout.
