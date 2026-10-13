#!/usr/bin/env python3
"""Atualiza o bloco de estatisticas do README do perfil usando a GitHub API.

Consulta a REST API de api.github.com, monta uma tabela em Markdown
e a injeta entre os marcadores STATS:START / STATS:END do README.md.

Nao tem dependencia externa: usa apenas a biblioteca padrao.

Variaveis de ambiente:
    GITHUB_TOKEN  token com escopo de leitura (o GITHUB_TOKEN do Actions serve)
    GITHUB_USER   login do dono do perfil (padrao: PedriSpengler)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

API = "https://api.github.com"
USER = os.environ.get("GITHUB_USER", "PedriSpengler")
TOKEN = os.environ.get("GITHUB_TOKEN")

START = "<!-- STATS:START -->"
END = "<!-- STATS:END -->"


def _request(url: str, data: dict | None = None) -> dict | list:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-updater")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def public_repos() -> list[dict]:
    """Todos os repositorios publicos do usuario, paginando."""
    repos: list[dict] = []
    page = 1
    while True:
        batch = _request(f"{API}/users/{USER}/repos?per_page=100&type=owner&page={page}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [r for r in repos if not r["private"]]


def merged_prs_elsewhere() -> int:
    """PRs mergeados em repositorios que nao sao do usuario."""
    q = f"type:pr author:{USER} is:merged is:public -user:{USER}"
    url = f"{API}/search/issues?q={urllib.parse.quote(q)}&per_page=1"
    return _request(url)["total_count"]


def contributed_repos() -> list[str]:
    """Repositorios de terceiros onde o usuario teve PR mergeado."""
    q = f"type:pr author:{USER} is:merged is:public -user:{USER}"
    url = f"{API}/search/issues?q={urllib.parse.quote(q)}&per_page=100"
    items = _request(url).get("items", [])
    seen = {it["repository_url"].split("/repos/")[1] for it in items}
    return sorted(seen)


def build_block(repos: list[dict], prs: int, contribs: list[str]) -> str:
    stars = sum(r["stargazers_count"] for r in repos)
    langs = Counter(r["language"] for r in repos if r["language"])
    top = ", ".join(f"{name} ({n})" for name, n in langs.most_common(5))
    updated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    lines = [
        START,
        "",
        "### 📊 Em números",
        "",
        "| | |",
        "|---|---|",
        f"| Repositórios públicos | **{len(repos)}** |",
        f"| Estrelas recebidas | **{stars}** |",
        f"| PRs mergeados em projetos de terceiros | **{prs}** |",
        f"| Linguagens mais usadas | {top or '—'} |",
    ]
    if contribs:
        links = ", ".join(f"[{c}](https://github.com/{c})" for c in contribs)
        lines.append(f"| Contribuições em open source | {links} |")
    lines += [
        "",
        f"<sub>Atualizado automaticamente via GitHub API em {updated}.</sub>",
        "",
        END,
    ]
    return "\n".join(lines)


def inject(readme: str, block: str) -> str:
    if START in readme and END in readme:
        head = readme.split(START)[0]
        tail = readme.split(END, 1)[1]
        return head + block + tail
    # primeira execucao: acrescenta ao final
    return readme.rstrip() + "\n\n---\n\n" + block + "\n"


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "README.md"
    try:
        repos = public_repos()
        prs = merged_prs_elsewhere()
        contribs = contributed_repos()
    except urllib.error.HTTPError as exc:
        print(f"erro da GitHub API: {exc.code} {exc.reason}", file=sys.stderr)
        return 1

    with open(path, encoding="utf-8") as fh:
        readme = fh.read()

    updated = inject(readme, build_block(repos, prs, contribs))

    if updated == readme:
        print("README já está atualizado.")
        return 0

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"README atualizado: {len(repos)} repos, {prs} PRs externos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
