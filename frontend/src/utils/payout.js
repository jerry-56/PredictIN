// Estimate this NEW order using the settlement formula and projected pools.
export function estimatePayout({ stake, side, yesPool, noPool }) {
    if (!['yes', 'no'].includes(side) || !Number.isFinite(stake) || stake <= 0) return null
    const winningPool = Number(side === 'yes' ? yesPool : noPool) + stake
    const losingPool = Number(side === 'yes' ? noPool : yesPool)
    const refund = winningPool < 100 || losingPool < 100
    const profitPool = refund ? 0 : Math.min(0.5 * winningPool, 0.9 * losingPool)
    const share = stake / winningPool
    const profit = Math.floor(share * profitPool * 100) / 100
    return { winningPool, losingPool, refund, profitPool, share, profit, payout: stake + profit }
}
