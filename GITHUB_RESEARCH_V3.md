# GitHub Research V3 - Migration Detection & Speed Optimizations

## Key Findings

### 1. Migration Detection - The Right Way
**Critical discovery:** Our current Geyser approach monitors `PUMP_AMM_PROGRAM_ID` for graduation, but the correct approach is to monitor the **Migration Wrapper Program**:
- `39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg` (migration authority)
- Log pattern: `"Program log: Instruction: Migrate"`
- This emits a structured event with token address, pool address, and liquidity amounts

### 2. Program IDs
| Program | ID |
|---------|-----|
| Pump.fun Main | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` |
| Migration Wrapper | `39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg` |
| PumpSwap AMM | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` |

### 3. Migration Event Data Layout (from chainstacklabs)
After base64-decoding `"Program data:"` line (skip 8-byte discriminator):
- timestamp (i64), index (u16), creator (32 bytes)
- **baseMint** (32 bytes) = TOKEN ADDRESS
- quoteMint (32 bytes), decimals (u8 x2)
- baseAmountIn (u64), quoteAmountIn (u64) = LIQUIDITY
- poolBaseAmount (u64), poolQuoteAmount (u64)
- minimumLiquidity (u64), initialLiquidity (u64)
- lpTokenAmountOut (u64), poolBump (u8)
- **pool** (32 bytes) = POOL ADDRESS

### 4. Three Detection Methods (fastest to slowest)
1. **logsSubscribe on migration wrapper** - catches `"Instruction: Migrate"` log
2. **programSubscribe on PumpSwap AMM** - watches for new pool accounts (244 bytes, SOL quote mint filter)
3. **Geyser transactionSubscribe** - what we currently use, highest volume but noisier

### 5. Speed Optimizations from Top Bots
- **No RPC calls at trade time** - all data from gRPC stream
- **Pre-computed PDAs** - derive bonding curve, vault addresses locally
- **PROCESSED commitment** (not CONFIRMED) for lowest latency
- **Racing transactions** - send to Jito, NextBlock, BloxRoute simultaneously
- **SkipPreflight: true** on transaction send
- **gRPC keepalive** at 10s intervals

### 6. Copy Trading Pattern (from coffellas)
```
accountInclude: [target_wallet_addresses]
accountRequired: [PUMP_FEE_ACCOUNT, PUMP_PROGRAM_ID]
```
Parse first 8 bytes for BUY/SELL discriminator, extract amounts from bytes 8-24.

### 7. Bonding Curve Constants
- Initial real token reserves: 793,100,000 (793.1M after 206.9M reserved for migration)
- Graduation SOL: ~85 SOL
- Complete flag: offset 48 in BC account data
- Progress = 100 - (real_token_reserves * 100 / 793,100,000)

## Implementation Priority
1. Add logsSubscribe migration listener (dedicated WS connection)
2. Parse migration event data for token + pool + liquidity
3. Open GRAD_SNIPE on migration with actual pool data
