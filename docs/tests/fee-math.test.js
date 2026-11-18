#!/usr/bin/env node
/*
 * docs/tests/fee-math.test.js — 验证 fee-math.js 的月度复利算对了。
 *
 * 执行： node docs/tests/fee-math.test.js
 * 退出码： 0 全部通过 / 1 有失败。不连网、无依赖。
 *
 * 三组「手算验证用例」(HAND-1/2/3) 的期望值不是从被测代码跑出来的，
 * 而是先用普通年金闭式解 FV = C × ((1+i)^n − 1) / i 手算好、写死在下面，
 * 再和逐月迭代的实现对比。每组都把中间步骤写在注释里，可用计算器复核。
 */
'use strict';

const M = require('../assets/fee-math.js');

let failures = 0;
function check(label, cond, extra) {
  console.log(`  [${cond ? 'ok ' : 'FAIL'}] ${label}${extra ? '  ' + extra : ''}`);
  if (!cond) failures++;
}
function near(actual, expected, tol, label) {
  const d = Math.abs(actual - expected);
  check(label, d <= tol, `实际=${actual.toFixed(6)} 期望=${expected.toFixed(6)} 差=${d.toExponential(2)}`);
}

console.log('== HAND-1 净回报为 0：复利退化成纯加总 ==');
/* 当前年龄 25 岁，月薪 20,000，预期年化回报 1.00%，两只基金 FER 都是 1.00%
 *   → 净年化 = 1.00 − 1.00 = 0  → 月利率 i = (1+0)^(1/12) − 1 = 0
 *   月供款 C = 20,000 × 5% × 2 = 2,000
 *   月数 n = (65 − 25) × 12 = 480
 *   手算 FV = C × n = 2,000 × 480 = 960,000（i = 0 时年金闭式解退化为加总）
 *   差额 = 0，比例 = 0%
 */
{
  const r = M.compare({ currentAge: 25, monthlySalary: 20000, ferCurrentPct: 1.0, ferAlternativePct: 1.0, annualReturnPct: 1.0 });
  check('月数 n = 480', r.months === 480, `实际=${r.months}`);
  check('月供款 C = 2000', r.contribution.total === 2000, `实际=${r.contribution.total}`);
  check('月利率 i = 0', r.current.monthlyRate === 0);
  near(r.current.balance, 960000, 1e-6, '当前基金累积 = 960,000');
  near(r.alternative.balance, 960000, 1e-6, '对比基金累积 = 960,000');
  near(r.difference, 0, 1e-9, '差额 = 0');
  near(r.ratioPct, 0, 1e-9, '比例 = 0%');
}

console.log('== HAND-2 12 个月短期，逐月可手算 ==');
/* 当前年龄 64 岁，月薪 30,000（刚好等于有关收入上限）
 *   月供款 C = 30,000 × 5% × 2 = 3,000（雇员 1,500 + 雇主 1,500）
 *   月数 n = (65 − 64) × 12 = 12
 *   预期年化回报 6.00%
 *   当前基金 FER = 6.00% → 净年化 0% → i = 0 → FV = 3,000 × 12 = 36,000
 *   对比基金 FER = 0.00% → 净年化 6% → i = 1.06^(1/12) − 1 = 0.0048675505653430
 *     FV = 3,000 × ((1+i)^12 − 1)/i = 3,000 × 0.06 / 0.0048675505653430
 *        = 3,000 × 12.32652834... = 36,979.585026
 *     （(1+i)^12 = 1.06 恰好成立，所以分子就是 0.06，这步可以直接核）
 *   差额 = 36,979.585026 − 36,000 = 979.585026
 *   比例 = 979.585026 / 36,979.585026 = 2.648989%
 */
{
  const r = M.compare({ currentAge: 64, monthlySalary: 30000, ferCurrentPct: 6.0, ferAlternativePct: 0.0, annualReturnPct: 6.0 });
  check('月数 n = 12', r.months === 12, `实际=${r.months}`);
  check('月供款 C = 3000（上限）', r.contribution.total === 3000 && r.contribution.capped === false, `实际=${r.contribution.total}`);
  near(r.alternative.monthlyRate, 0.0048675505653430, 1e-15, '月利率 i = 0.0048675505653430');
  near(r.current.balance, 36000, 1e-6, '当前基金累积 = 36,000');
  near(r.alternative.balance, 36979.585026, 1e-5, '对比基金累积 = 36,979.585026');
  near(r.difference, 979.585026, 1e-5, '差额 = 979.585026');
  near(r.ratioPct, 2.648989, 1e-5, '比例 = 2.648989%');
}

console.log('== HAND-3 30 年、两档真实 FER ==');
/* 当前年龄 35 岁，月薪 50,000（高于上限，按 30,000 计）
 *   月供款 C = 30,000 × 5% × 2 = 3,000
 *   月数 n = (65 − 35) × 12 = 360
 *   预期年化回报 5.00%
 *   当前基金 FER = 1.60% → 净年化 3.40%
 *     i_A = 1.034^(1/12) − 1 = 0.00279011649053218
 *     FV_A = 3,000 × ((1+i_A)^360 − 1)/i_A
 *          = 3,000 × (1.034^30 − 1)/i_A = 3,000 × 1.7259657.../0.00279011649053218
 *          = 1,856,446.067356
 *   对比基金 FER = 0.80% → 净年化 4.20%
 *     i_B = 1.042^(1/12) − 1 = 0.00343437929004682
 *     FV_B = 3,000 × (1.042^30 − 1)/i_B = 3,000 × 2.4360464.../0.00343437929004682
 *          = 2,127,746.251893
 *   差额 = 2,127,746.251893 − 1,856,446.067356 = 271,300.184537
 *   比例 = 271,300.184537 / 2,127,746.251893 = 12.750589%
 *   （总供款只有 3,000 × 360 = 1,080,000，差额已超过供款总额的四分之一）
 */
{
  const r = M.compare({ currentAge: 35, monthlySalary: 50000, ferCurrentPct: 1.6, ferAlternativePct: 0.8, annualReturnPct: 5.0 });
  check('月数 n = 360', r.months === 360, `实际=${r.months}`);
  check('月薪触及上限', r.contribution.total === 3000 && r.contribution.capped === true);
  near(r.current.monthlyRate, 0.00279011649053218, 1e-15, '月利率 i_A');
  near(r.alternative.monthlyRate, 0.00343437929004682, 1e-15, '月利率 i_B');
  near(r.current.balance, 1856446.067356, 1e-4, '当前基金累积 = 1,856,446.067356');
  near(r.alternative.balance, 2127746.251893, 1e-4, '对比基金累积 = 2,127,746.251893');
  near(r.difference, 271300.184537, 1e-4, '差额 = 271,300.184537');
  near(r.ratioPct, 12.750589, 1e-6, '比例 = 12.750589%');
  near(r.totalContributed, 1080000, 1e-9, '总供款 = 1,080,000');
}

console.log('== 交叉验算：逐月迭代 vs 闭式年金解 ==');
/* 实现用的是逐月迭代，这里用闭式解在多组参数上独立对一遍。 */
{
  const cases = [
    { months: 1, annualReturnPct: 5, ferPct: 1 },
    { months: 12, annualReturnPct: 5, ferPct: 1.2252 },
    { months: 120, annualReturnPct: 7, ferPct: 2.87928 },
    { months: 360, annualReturnPct: 5, ferPct: 0.537 },
    { months: 480, annualReturnPct: 3, ferPct: 1.5 },
    { months: 480, annualReturnPct: 1, ferPct: 2.5 },   // 净年化为负
    { months: 240, annualReturnPct: 0, ferPct: 0 },      // i = 0
  ];
  for (const c of cases) {
    const opts = { monthlyContribution: 3000, months: c.months, annualReturnPct: c.annualReturnPct, ferPct: c.ferPct };
    const iter = M.accumulate(opts).balance;
    const closed = M.accumulateClosedForm(opts);
    const tol = Math.max(1e-6, Math.abs(closed) * 1e-12);
    check(`n=${c.months} 回报=${c.annualReturnPct}% FER=${c.ferPct}% 迭代≈闭式`,
      Math.abs(iter - closed) <= tol, `迭代=${iter.toFixed(6)} 闭式=${closed.toFixed(6)}`);
  }
}

console.log('== 月利率几何折算：12 个月复利回到净年化 ==');
{
  for (const net of [5, 3.44, 0, -1.5, 12]) {
    const i = M.monthlyRate(net);
    near(Math.pow(1 + i, 12), 1 + net / 100, 1e-12, `(1+i)^12 = 1 + ${net}%`);
  }
}

console.log('== 供款上下限（法定参数，非数据集字段）==');
{
  check('月薪 30,000 → 3,000', M.monthlyContribution(30000).total === 3000);
  check('月薪 80,000 → 3,000（封顶）', M.monthlyContribution(80000).total === 3000);
  const low = M.monthlyContribution(6000);
  check('月薪 6,000 → 雇员 0、雇主 300', low.employee === 0 && low.employer === 300 && low.total === 300,
    `实际 employee=${low.employee} employer=${low.employer}`);
  const at = M.monthlyContribution(7100);
  check('月薪 7,100 → 雇员 355、雇主 355', at.employee === 355 && at.employer === 355);
  check('月薪 0 → 0', M.monthlyContribution(0).total === 0);
}

console.log('== 边界 ==');
{
  check('年龄 65 → 月数 0', M.monthsToRetirement(65) === 0);
  check('年龄 70 → 月数 0', M.monthsToRetirement(70) === 0);
  const r = M.compare({ currentAge: 65, monthlySalary: 30000, ferCurrentPct: 1.6, ferAlternativePct: 0.8, annualReturnPct: 5 });
  check('65 岁：累积与差额均为 0', r.current.balance === 0 && r.difference === 0 && r.ratioPct === 0);
  const same = M.compare({ currentAge: 30, monthlySalary: 25000, ferCurrentPct: 1.1, ferAlternativePct: 1.1, annualReturnPct: 5 });
  near(same.difference, 0, 1e-9, '两只 FER 相同 → 差额 0');
  const worse = M.compare({ currentAge: 30, monthlySalary: 25000, ferCurrentPct: 0.8, ferAlternativePct: 1.8, annualReturnPct: 5 });
  check('对比基金 FER 更高 → 差额为负', worse.difference < 0, `差额=${worse.difference.toFixed(2)}`);
  check('差额为负时比例仍为正', worse.ratioPct > 0, `比例=${worse.ratioPct.toFixed(4)}%`);
}

console.log(failures === 0 ? '\n全部通过。' : `\n${failures} 项失败。`);
process.exit(failures === 0 ? 0 : 1);
