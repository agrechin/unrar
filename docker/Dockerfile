FROM rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667 AS actionlint

FROM ubuntu:26.04@sha256:da6fc2be547864451aa253836dd926da33623312df4a9a243e35dc877c378a78

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       clang-21 lld-21 llvm-21 make python3 shellcheck ruby ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=actionlint /usr/local/bin/actionlint /usr/local/bin/actionlint
ENV PATH="/usr/lib/llvm-21/bin:${PATH}"
WORKDIR /src
