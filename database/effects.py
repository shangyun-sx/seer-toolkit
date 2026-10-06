"""
技能效果解析器 —— 把效果模板渲染成中文描述
==========================================

游戏把技能效果拆成三层，和 SeerAPI 的
`SkillEffectType` / `SkillEffectParam` / `SkillEffectInUse` 是一一对应的：

    EffectInfo.db / Effect      效果模板，如 '技能使用成功时，{1}%改变自身{0}等级{2}'
    EffectInfo.db / ParamType   参数取值表，如 '攻击|防御|特攻|特防|速度|命中'
    Moves.db / moves            技能挂了哪些效果、参数是什么
        SideEffect    = '4 '          空格分隔的效果 ID 列表
        SideEffectArg = '0 20 1 '     按各效果 argsNum **顺序拼接**的参数

渲染 钢之爪（SideEffect='4', SideEffectArg='0 20 1'）:

    {0}=0  → 紧跟「自身…等级」，查六维表 → 攻击
    {1}=20 → 普通数字
    {2}=1  → 紧跟「等级」，是增量，补正号 → +1
    → 技能使用成功时，20%改变自身攻击等级+1

几个必须在真实数据上验证过才知道的坑：

  * 任何 `{n}` 都有 `n < argsNum`（2380 行零例外），所以按模板取值永远安全。
    但反过来**不成立** —— 57 个效果的 argsNum 大于模板实际用到的参数，多出来的
    是内部参数不显示。所以**不能从 argsNum 反推模板要几个占位符**。
  * 约 90% 的占位符是纯数字，只有约 10% 需要查表，且集中在两类：
    「…等级」→ 六维表，「令对方…」→ 异常状态表。
  * 判断顺序必须**先六维、后状态**：`使自身{2}提升1个等级` 里的 {2} 前面是
    「使自身」（看着像状态），但后面是「提升…等级」（其实是六维）。
  * `SideEffect` 是**多个不同效果**的顺序列表，参数按各自 argsNum 顺序消费；
    `龙之意志` 的 `SideEffect='4 4 4 4 4 '` 只是「同一个效果重复 5 次」的特例，
    不需要单独分支。
  * 本地 EffectInfo.db 缺了 213 个 id，其中 5 个被技能引用（**id=31 被 303 个
    技能引用**）。这些用 `_SUPPLEMENTAL_EFFECTS` 补上，见下方注释。

数据来源: https://api.seerapi.com/v1/skill_effect_type/<id>
"""

import re
import sqlite3
import threading
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from database.connections import ThreadLocalConnections
except ImportError:  # 直接运行 database/effects.py 时
    from connections import ThreadLocalConnections

# ──────────────────────────────────────────
#  常量
# ──────────────────────────────────────────

#: 六维表。id 0 / 2 / 16 / 24 内容完全相同，取一个即可
_SIX_DIM_PARAM = 0

#: 异常状态表
_STATUS_PARAM = 1

#: 「令/使 + 对象」—— 后面若直接跟槽位且不是数量词，就是异常状态
_STATUS_PREFIXES = (
    '令对方', '令对手', '令自身', '令自己',
    '使对方', '使对手', '使自身', '使自己',
)

#: 「提升/降低…若干字…(个)等级」→ 该槽是六维。
#: 用来兜住 `使自身{2}提升1个等级` 这种槽位和「等级」之间夹了数字的写法
_SIX_DIM_VERB_RE = re.compile(r'^(?:提升|提高|降低|下降|减少|增加).{0,3}个?等级')

#: 状态槽后面紧跟这些字，说明其实是数量词/概率，不是异常状态
_STATUS_STOP = ('种', '项', '回合', '能力', '概率', '%')

_PLACEHOLDER_RE = re.compile(r'\{(\d+)\}')

#: 本地 EffectInfo.db 缺失、但技能里确实引用到的效果定义。
#: 数据来源: https://api.seerapi.com/v1/skill_effect_type/<id>
#: （已核对 API 与本地的 argsNum / info 在 17 个抽样 id 上逐字节一致，
#:   所以这些补充定义和本地是同一版本，可以放心用）
_SUPPLEMENTAL_EFFECTS: Dict[int, Tuple[int, str]] = {
    31: (2, '1回合做{0}次攻击'),                      # 303 个技能在用，缺了会大面积崩
    21: (3, '作用{0}回合，每回合反弹对手1/{2}的伤害'),
    42: (2, '{0}回合自己使用电招式伤害×2'),
    41: (2, '{0}回合本方受到的火系攻击伤害减半'),
    174: (5, '{0}回合内，若对手使用属性攻击则{3}%自身{1}等级+{4}'),
}


class EffectParser:
    """技能效果解析器：效果模板 + 技能参数 → 中文描述。

        parser = EffectParser('data')
        parser.render_move('4 ', '0 20 1 ')   # ['技能使用成功时，20%改变自身攻击等级+1']
        parser.describe('4 5 ', '0 20 1 5 15 -1')
    """

    def __init__(self, data_dir: str):
        """
        data_dir: 包含 EffectInfo.db 的目录
        """
        self.data_dir = data_dir
        # 连接按线程各持一条 —— Pokedex.effects 是跨线程共享的，共享一条
        # 连接在并发下会读到彼此的中间状态
        self._conns = ThreadLocalConnections(data_dir)
        self._effects: Dict[int, Dict] = {}
        self._param_types: Dict[int, List[str]] = {}
        self._loaded = False
        self._load_lock = threading.Lock()

    # ──────────────────────────────────────────
    #  数据库连接管理
    # ──────────────────────────────────────────

    @property
    def effect_db(self) -> sqlite3.Connection:
        return self._conns.get('EffectInfo.db')

    def close(self) -> None:
        """关闭数据库连接并清空缓存"""
        self._conns.close()
        self._effects = {}
        self._param_types = {}
        self._loaded = False

    # ──────────────────────────────────────────
    #  装载
    # ──────────────────────────────────────────

    def _load(self) -> None:
        """一次性把效果表和参数表读进内存（实测约 10ms，几百 KB）。

        带锁做双重检查：两个线程同时首次调用时，只让一个真去读，
        其余等它读完直接用结果，免得重复装载、也免得读到半份数据。
        """
        if self._loaded:
            return

        with self._load_lock:
            if self._loaded:      # 等锁期间已经被别的线程装好了
                return
            self._load_locked()

    def _load_locked(self) -> None:
        """真正的装载逻辑，调用方必须已经持有 `_load_lock`。"""
        self._param_types = {
            row['id']: (row['params'] or '').split('|')
            for row in self.effect_db.execute('SELECT id, params FROM ParamType')
        }

        effects: Dict[int, Dict] = {}
        for row in self.effect_db.execute(
                'SELECT id, argsNum, info, analyze FROM Effect'):
            effects[row['id']] = {
                'argsNum': row['argsNum'] or 0,
                'info': row['info'] or '',
                'analyze': row['analyze'] or '',
                'supplemental': False,
            }

        # 补上本地缺失、但技能引用到的效果
        for effect_id, (args_num, info) in _SUPPLEMENTAL_EFFECTS.items():
            if effect_id not in effects:
                effects[effect_id] = {
                    'argsNum': args_num,
                    'info': info,
                    'analyze': '',
                    'supplemental': True,
                }

        # 预编译参数类型，避免每次渲染都重跑正则
        for effect in effects.values():
            effect['scheme'] = self.infer_scheme(effect['info'])

        self._effects = effects
        self._loaded = True

    def effect(self, effect_id: int) -> Optional[Dict]:
        """按 ID 取效果定义（含预编译的 scheme）"""
        self._load()
        return self._effects.get(effect_id)

    def param_values(self, param_id: int) -> List[str]:
        """取某张参数取值表"""
        self._load()
        return self._param_types.get(param_id, [])

    def count(self) -> int:
        """效果总数（含补充的）"""
        self._load()
        return len(self._effects)

    # ──────────────────────────────────────────
    #  参数类型推断
    # ──────────────────────────────────────────

    @staticmethod
    def infer_scheme(info: str) -> Dict[str, Tuple[str, bool]]:
        """从模板文本推断每个 `{n}` 该查哪张表、是否需要补正号。

        只看占位符**自己**的上下文，**绝不看 argsNum**（57 个效果的 argsNum
        大于实际用量，反推会错）。

        返回: {槽位号: (kind, needs_sign)}，kind 取值 'stat' / 'status' / 'num'
        """
        scheme: Dict[str, Tuple[str, bool]] = {}

        for match in _PLACEHOLDER_RE.finditer(info):
            slot = match.group(1)
            # 占位符前 4 个字、后 8 个字，判断语义用这点上下文足够了
            prefix = info[max(0, match.start() - 4):match.start()]
            suffix = info[match.end():match.end() + 8]

            # 顺序很重要：先判六维，再判状态。
            # `使自身{2}提升1个等级` 的 {2} 前缀像状态、后缀是等级 —— 必须判成六维
            if suffix.startswith('等级') or _SIX_DIM_VERB_RE.match(suffix):
                kind = 'stat'
            elif suffix.startswith('状态'):
                kind = 'status'
            elif (any(prefix.endswith(p) for p in _STATUS_PREFIXES)
                  and not suffix.startswith(_STATUS_STOP)):
                kind = 'status'
            else:
                kind = 'num'

            # 紧跟「等级」的那一格是等级增量，正数要补 '+'
            scheme[slot] = (kind, prefix.endswith('等级'))

        return scheme

    # ──────────────────────────────────────────
    #  取值与兜底
    # ──────────────────────────────────────────

    def _lookup(self, param_id: int, raw: str) -> Optional[str]:
        """按整数下标查表。越界 / 空串 / 占位符 'XX' 都返回 None 交给调用方兜底。"""
        try:
            index = int(raw)
        except (TypeError, ValueError):
            return None

        values = self.param_values(param_id)
        if 0 <= index < len(values) and values[index] not in ('', 'XX'):
            return values[index]
        return None

    @staticmethod
    def _numeric(raw: str, needs_sign: bool) -> str:
        """紧跟「等级」的增量槽：正数补 '+'，负数原样输出。"""
        if not needs_sign:
            return raw
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return raw
        return f'+{value}' if value > 0 else str(value)

    def _format_value(self, kind: str, raw: str, needs_sign: bool) -> str:
        """把一个参数渲染成文案。任何查不到的情况都退化成原值，绝不抛异常。"""
        if kind == 'stat':
            return self._lookup(_SIX_DIM_PARAM, raw) or self._numeric(raw, needs_sign)
        if kind == 'status':
            # 状态名不补正号
            return self._lookup(_STATUS_PARAM, raw) or raw
        return self._numeric(raw, needs_sign)

    # ──────────────────────────────────────────
    #  渲染
    # ──────────────────────────────────────────

    def split_arg_groups(self, effect_ids: Sequence[int],
                         args: Sequence[str]) -> List[Tuple[int, List[str]]]:
        """把 `SideEffect` + `SideEffectArg` 切成 [(效果 ID, 该效果的参数), ...]。

        已知效果按自己的 argsNum 顺序消费参数；完全未知的效果平分剩余参数，
        这样至少不会让后面的已知效果整体错位。
        """
        self._load()

        known_args = sum(self._effects[e]['argsNum']
                         for e in effect_ids if e in self._effects)
        unknown_count = sum(1 for e in effect_ids if e not in self._effects)
        budget = max(0, len(args) - known_args)
        share = budget // unknown_count if unknown_count else 0

        groups: List[Tuple[int, List[str]]] = []
        pos = 0
        for effect_id in effect_ids:
            effect = self._effects.get(effect_id)
            size = effect['argsNum'] if effect else share
            chunk = list(args[pos:pos + size])
            pos += len(chunk)          # 按实际取到的数量前进，参数不够也不会越界
            groups.append((effect_id, chunk))

        # 数据里偶尔会「效果列表少写一项」，参数比效果多出整数组。
        # 例: 龙之意志 SE='4 4 4 4 4' 但参数给了 6 组（攻/防/特攻/特防/速度/命中），
        # 少写了一个 '4'。这时把多出来的整组继续套用最后一个效果。
        # 守卫条件保证不会误伤另外两类畸形：末尾 argsNum=0 时跳过（多余参数本就
        # 该忽略），剩余不是整数倍时跳过（真畸形，不动）。
        last_id = effect_ids[-1]
        last_size = self._effects[last_id]['argsNum'] if last_id in self._effects else 0
        while last_size > 0 and len(args) - pos >= last_size:
            groups.append((last_id, list(args[pos:pos + last_size])))
            pos += last_size

        return groups

    def render_effect(self, effect_id: int, args: Sequence[str]) -> Optional[str]:
        """渲染单个效果。效果不存在或没有文案时返回 None。"""
        self._load()
        effect = self._effects.get(effect_id)
        if effect is None or not effect['info']:
            return None

        scheme = effect['scheme']

        def _replace(match: 're.Match') -> str:
            slot = match.group(1)
            index = int(slot)
            # 参数不够时显示 '?'，而不是抛 IndexError
            raw = args[index] if index < len(args) else '?'
            kind, needs_sign = scheme.get(slot, ('num', False))
            return self._format_value(kind, raw, needs_sign)

        return _PLACEHOLDER_RE.sub(_replace, effect['info'])

    def render_move(self, side_effect, side_effect_arg) -> List[str]:
        """渲染一个技能的**全部**效果，返回描述列表。

        对应 SeerAPI 的 `Skill.skill_effect`（一个技能挂多条效果）。
        """
        self._load()

        ids = [int(token) for token in str(side_effect or '').split()]
        args = str(side_effect_arg or '').split()
        if not ids:
            return []

        texts: List[str] = []
        for effect_id, chunk in self.split_arg_groups(ids, args):
            text = self.render_effect(effect_id, chunk)
            if text:
                texts.append(text)
            elif effect_id not in self._effects:
                # 缺失的效果 ID 也要显示出来，不能静默吞掉
                texts.append(f'[未知效果#{effect_id}]')
        return texts

    def describe(self, side_effect, side_effect_arg) -> str:
        """渲染成一行文本，多个效果用「；」连接"""
        return '；'.join(self.render_move(side_effect, side_effect_arg))


# ──────────────────────────────────────────
#  独立运行：快速测试
# ──────────────────────────────────────────
if __name__ == '__main__':
    import sys

    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    data_dir = sys.argv[1] if len(sys.argv) > 1 else 'data'
    parser = EffectParser(data_dir)

    print(f"效果总数: {parser.count()}\n")

    print("-- 已验证的样例 --")
    samples = [
        (4, ['2', '100', '-1'], '技能使用成功时，100%改变自身特攻等级-1'),
        (5, ['5', '15', '-1'], '技能使用成功时，15%改变对手命中等级-1'),
        (6, ['4'], '对方所受伤害的1/4会反弹给自己'),
        (110, ['3', '100', '5'], '3回合内每次躲避攻击都有100%概率使自身命中提升1个等级'),
        (149, ['50', '0', '50', '1'], '命中后，50%令对方麻痹，50%令对方中毒'),
        (196, ['5', '10', '-1', '5', '20', '-2'],
         '10%令对方命中等级-1；若先出手，则20%使对方命中等级-2'),
        (31, ['2', '5'], '1回合做2次攻击'),
    ]
    for effect_id, args, expected in samples:
        got = parser.render_effect(effect_id, args)
        mark = '✅' if got == expected else '❌'
        print(f"  {mark} eff{effect_id} {args}")
        print(f"      {got}")
        if got != expected:
            print(f"      期望: {expected}")

    print("\n-- 多效果顺序消费 + 补渲染（效果列表漏写一项）--")
    print("  龙之意志:")
    for line in parser.render_move(
            '4 4 4 4 4 ',
            '0 100 1 1 100 1 2 100 1 3 100 1 4 100 1 5 100 1 '):
        print(f"      • {line}")

    parser.close()
