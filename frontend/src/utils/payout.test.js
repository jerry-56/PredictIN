import test from 'node:test'
import assert from 'node:assert/strict'
import { estimatePayout } from './payout.js'

test('2000 winning stake against 100 returns 2090', () => {
    assert.equal(estimatePayout({ stake: 2000, side: 'yes', yesPool: 0, noPool: 100 }).payout, 2090)
})
test('100 winning stake against 2000 is capped at 150', () => {
    assert.equal(estimatePayout({ stake: 100, side: 'no', yesPool: 2000, noPool: 0 }).payout, 150)
})
test('existing same-side stakes dilute the new order share', () => {
    assert.equal(estimatePayout({ stake: 2000, side: 'no', yesPool: 100, noPool: 500 }).payout, 2072)
})
test('missing or below-minimum opposition means refund', () => {
    for (const yesPool of [0, 99]) {
        const result = estimatePayout({ stake: 2000, side: 'no', yesPool, noPool: 500 })
        assert.equal(result.refund, true)
        assert.equal(result.payout, 2000)
    }
})
