# GitHub Research V5 - PumpSwap Pool Price Decoding

## Key Finding
PumpSwap pool accounts do NOT contain reserves. They store vault addresses.
To get price: read SPL token balances from vault accounts.

## Pool Account Layout (after 8-byte Anchor discriminator)
| Offset | Size | Field |
|--------|------|-------|
| 8 | 1 | pool_bump |
| 9 | 2 | index |
| 11 | 32 | creator |
| 43 | 32 | base_mint (TOKEN) |
| 75 | 32 | quote_mint (SOL) |
| 107 | 32 | lp_mint |
| 139 | 32 | pool_base_token_account (TOKEN VAULT) |
| 171 | 32 | pool_quote_token_account (SOL VAULT) |
| 203 | 8 | lp_supply |
| 211 | 32 | coin_creator (new pools only) |

## Price Formula
price = quote_vault_balance / base_vault_balance
(SOL amount / token amount = price per token in SOL)

## Live Price Monitoring (from pumpswap-watcher)
1. Decode pool account to get vault addresses
2. Subscribe via accountSubscribe to both vaults
3. Parse SPL token amount at offset 64 in account data
4. Calculate price on every update

## pumpswapamm package (PyPI)
- fetch_pool_base_price(pool_address) → (price, base_balance, quote_balance)
- Uses get_multiple_accounts_json_parsed on vault accounts
