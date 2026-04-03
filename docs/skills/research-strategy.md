---
name: research-strategy
description: Research trading strategies using GitHub repos, academic papers, and real bot performance data
---

# Research Strategy

Use when we need to find new approaches or validate existing ones.

## Process
1. Define the question (e.g., "how do profitable bots detect dips?")
2. Search GitHub for repos with real implementations
3. Search web for backtested results and academic papers
4. Extract concrete algorithms (not theory)
5. Check if we already have the infrastructure to implement
6. Calculate expected P&L before implementing (Rule 5: test math first)
7. Document in docs/research/ with sources

## Key Sources
- GitHub: freqtrade strategies, NostalgiaForInfinity, jesse-ai
- Research: ChainCatcher smart wallet analysis, Helius MEV reports
- APIs: Jupiter docs, DEXScreener docs, Helius docs

## Rules (from ERROR_LOG.md)
- Rule 1: Calculate breakeven BEFORE setting any TP
- Rule 5: Test with math first
- Rule 11: Batch API calls
- Always check ITERATION_LOG.md for what we already tried
