import {expect, test} from 'vitest';
import {indexFailure} from './indexFailure';

test('unknown and inherited property names receive safe fallback advice', () => {
  for (const code of [null, 'future_error', '__proto__', 'constructor']) {
    expect(indexFailure(code).reason).toBe('其他失败原因');
  }
  expect(indexFailure('model_daily_quota_exceeded').suggestion).toContain('UTC');
  expect(indexFailure('credential_missing').suggestion).toContain('Worker');
});
