# Live claim generation adapter

The production composition root injects a structured transport into
`OpenAICompatibleClaimGenerator`; this package deliberately contains no vendor
SDK, global client or secret lookup. The versioned prompt and strict Pydantic
schema own the output contract. Any transport error, schema drift, external
identifier, missing span or whitelist escape fails closed.
