/*!
 * fee-math.js — 强积金费用终身成本计算核心
 *
 * 纯计算，无 DOM 依赖。浏览器里挂到 window.MpfFeeMath，Node 里走 module.exports，
 * 同一份代码同时给页面和 site/tests/fee-math.test.js 使用。
 *
 * ── 假设与出处 ───────────────────────────────────────────────────────────
 * 1) 供款规则来自《强制性公积金计划条例》的法定参数，**不在**
 *    data/funds_latest.json 里（该数据集只有基金层面的费用与回报字段，
 *    没有任何供款上下限字段，已逐字段核对）。因此以下三个数字是本计算器
 *    写死的假设，若法例修订需要同步更新：
 *      - 雇员、雇主各按有关收入的 5% 作强制性供款（CONTRIB_RATE = 0.05）
 *      - 有关收入上限 月薪 30,000 港元 → 每方每月供款上限 1,500 港元
 *        （INCOME_CAP_MONTHLY = 30000）
 *      - 有关收入下限 月薪 7,100 港元 → 低于此数雇员**无须**供款，
 *        雇主仍须供 5%（INCOME_FLOOR_MONTHLY = 7100）
 *    自愿性供款、特别自愿性供款、按年薪计的安排都不在模型内。
 * 2) 退休年龄固定 65 岁（RETIREMENT_AGE），供款月数 = (65 − 当前年龄) × 12。
 * 3) 月度复利。净年化回报 = 预期年化回报率 − 基金开支比率（FER），
 *    月利率 i = (1 + 净年化/100)^(1/12) − 1（几何折算，使 12 个月复利后
 *    恰好等于净年化）。
 * 4) 供款在每月月末投入（普通年金 / ordinary annuity）：
 *    余额 = 余额 × (1 + i) + 月供款，逐月迭代 n 次。
 *    闭式解 FV = C × ((1 + i)^n − 1) / i，i = 0 时 FV = C × n。
 * 5) 模型不含现有累算权益（起始余额按 0 计）、不含薪金增长、
 *    不含通胀调整、不含基金转换的时间差；FER 与回报率全程不变。
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.MpfFeeMath = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var RETIREMENT_AGE = 65;
  var CONTRIB_RATE = 0.05;          // 雇员 5% + 雇主 5%
  var INCOME_CAP_MONTHLY = 30000;   // 有关收入上限（月）
  var INCOME_FLOOR_MONTHLY = 7100;  // 有关收入下限（月）

  /** 月供款总额（雇员 + 雇主），已套用上下限。 */
  function monthlyContribution(monthlySalary) {
    var s = Number(monthlySalary);
    if (!isFinite(s) || s <= 0) return { employee: 0, employer: 0, total: 0, capped: false };
    var base = Math.min(s, INCOME_CAP_MONTHLY);
    var employer = base * CONTRIB_RATE;
    // 月薪低于有关收入下限：雇员免供，雇主照供。
    var employee = s < INCOME_FLOOR_MONTHLY ? 0 : base * CONTRIB_RATE;
    return {
      employee: employee,
      employer: employer,
      total: employee + employer,
      capped: s > INCOME_CAP_MONTHLY,
      belowFloor: s < INCOME_FLOOR_MONTHLY
    };
  }

  /** 供款月数：(65 − 年龄) × 12，已到或超过 65 岁则为 0。 */
  function monthsToRetirement(currentAge) {
    var a = Number(currentAge);
    if (!isFinite(a)) return 0;
    return Math.max(0, Math.round((RETIREMENT_AGE - a) * 12));
  }

  /** 净年化（%）→ 月利率。 */
  function monthlyRate(netAnnualPct) {
    var net = Number(netAnnualPct) / 100;
    if (net <= -1) return -1; // 净年化 ≤ −100%，退化情形
    return Math.pow(1 + net, 1 / 12) - 1;
  }

  /**
   * 月度复利累积（每月月末供款）。
   * @returns {{balance:number, contributed:number, monthlyRate:number, netAnnualPct:number}}
   */
  function accumulate(opts) {
    var C = Number(opts.monthlyContribution) || 0;
    var n = Math.max(0, Math.round(Number(opts.months) || 0));
    var netAnnualPct = Number(opts.annualReturnPct) - Number(opts.ferPct);
    var i = monthlyRate(netAnnualPct);
    var balance = 0;
    for (var m = 0; m < n; m++) {
      balance = balance * (1 + i) + C;
    }
    return {
      balance: balance,
      contributed: C * n,
      monthlyRate: i,
      netAnnualPct: netAnnualPct
    };
  }

  /** 闭式解，供测试独立交叉验算。 */
  function accumulateClosedForm(opts) {
    var C = Number(opts.monthlyContribution) || 0;
    var n = Math.max(0, Math.round(Number(opts.months) || 0));
    var i = monthlyRate(Number(opts.annualReturnPct) - Number(opts.ferPct));
    if (i === 0) return C * n;
    return C * (Math.pow(1 + i, n) - 1) / i;
  }

  /**
   * 两只基金的终身费用差额。
   * @param {{currentAge:number, monthlySalary:number, ferCurrentPct:number,
   *          ferAlternativePct:number, annualReturnPct:number}} input
   */
  function compare(input) {
    var contrib = monthlyContribution(input.monthlySalary);
    var months = monthsToRetirement(input.currentAge);
    var shared = { monthlyContribution: contrib.total, months: months, annualReturnPct: input.annualReturnPct };

    var current = accumulate({
      monthlyContribution: shared.monthlyContribution, months: months,
      annualReturnPct: input.annualReturnPct, ferPct: input.ferCurrentPct
    });
    var alternative = accumulate({
      monthlyContribution: shared.monthlyContribution, months: months,
      annualReturnPct: input.annualReturnPct, ferPct: input.ferAlternativePct
    });

    var difference = alternative.balance - current.balance;
    // 比例基准 = 两者中较高的累积金额（差额占「费用较低一方」的百分比）。
    var higher = Math.max(current.balance, alternative.balance);
    var ratioPct = higher > 0 ? (Math.abs(difference) / higher) * 100 : 0;

    return {
      months: months,
      years: months / 12,
      contribution: contrib,
      current: current,
      alternative: alternative,
      difference: difference,
      absDifference: Math.abs(difference),
      ratioPct: ratioPct,
      higherBalance: higher,
      totalContributed: current.contributed
    };
  }

  return {
    RETIREMENT_AGE: RETIREMENT_AGE,
    CONTRIB_RATE: CONTRIB_RATE,
    INCOME_CAP_MONTHLY: INCOME_CAP_MONTHLY,
    INCOME_FLOOR_MONTHLY: INCOME_FLOOR_MONTHLY,
    monthlyContribution: monthlyContribution,
    monthsToRetirement: monthsToRetirement,
    monthlyRate: monthlyRate,
    accumulate: accumulate,
    accumulateClosedForm: accumulateClosedForm,
    compare: compare
  };
});
