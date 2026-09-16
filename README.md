# 居灵 TakeHome：轮廓内矩形物体摆放

## 1. AI 使用说明

本题鼓励使用 AI 工具。本次作答使用情况如下：

1. **使用了哪些 AI 工具**  
   Cursor（对话模型：Grok）。

2. **AI 主要帮助了哪些部分**  
   - 把题目约束拆成可实现的几何模块（轮廓包含、门禁区、贴墙滑动、碰撞）。  
   - 生成 Python 工程骨架、可视化与命令行入口。  
   - 根据四个 `example*.json` 的运行结果做 Debug（例如候选全挤在墙角、冰箱净空与内开门扇区打架）。

3. **哪些关键逻辑是自己理解并调整的**  
   - **内开门 1×1**：按门宽 N 为 1 个单位，禁区是房间内侧的 **N×N 正方形**。  
   - **冰箱开门边**：`length` 的一条边是开门边 ⇒ 贴墙时 **length 沿墙**、开门朝室内；该侧 80mm 内不能放任何物体（含离地架）。  
   - **离地架**：仍须贴墙、与轮廓平行/垂直，且 **2D 上不得与任何其他物体重叠**（题目未给叠放例外）。  
   - **空间足够则全部贴墙**：沿墙按物体长度铺不重叠槽位再回溯。  
   - **斜墙**：旋转角等于墙角（或 +90°），不只允许 0°/90°；贴墙时微内收 0.5mm，避免斜边转角处穿出轮廓。

---

## 2. 题目在实现里怎么落地

给定闭合轮廓、门、以及若干 `[length, width]` 矩形，在轮廓内摆放：

| 约束 | 实现 |
| --- | --- |
| 不与轮廓/其它物体重叠 | 多边形包含（越界面积 ≤1 mm²）；任意两件相交面积 >1 mm² 即非法；允许边贴边 |
| 可旋转但须与轮廓边平行或垂直 | 贴墙时旋转角 = 墙方向角（或 +90°） |
| 空间足够优先贴墙 | 候选从墙段生成，中心 = 墙脚点 + 内法向 × (半进深 + 0.5mm) |
| 不可挡门；内开门占 N×N | 门缝缓冲带；`isOpenInward=true` 时再并上内侧 N×N 正方形 |
| 冰箱开门边不能放东西 | 开门朝室内的 80mm 条带内禁止再放任何物体 |
| 货架边可以放东西 | 货架之间允许共边贴紧 |
| 离地架 | 同样占 2D 面积、同样贴墙，不得与冰箱/货架/其他离地架重叠 |

旋转约定：输入尺寸在 **0°** 时 `length` 沿 +x、`width` 沿 +y；输出角度为逆时针度数。

坐标单位与输入 JSON 一致（毫米）。

### 算法流程

```
读入 JSON → 规范化多边形（自交则 buffer(0)）
         → 挖掉门洞后的可贴墙段（共线墙合并）
         → 构造门禁区
         → 按 fridge → iceMaker → shelf → overShelf 顺序
         → 沿墙生成槽位候选（浅进深优先）
         → 回溯搜索，直到全部放下
         → 硬约束复查 → 写出 JSON / PNG
```

核心代码：

- `src/geom.py`：多边形、门禁区、贴墙矩形  
- `src/placer.py`：候选生成与回溯  
- `src/validate.py`：结果复查  
- `src/viz.py`：可视化  

---

## 3. 运行环境及运行方式

- Python 3.10+（在 Windows / Python 3.12 下验证通过）  
- 依赖：`shapely`、`matplotlib`、`numpy`

```bash
cd 居灵-TakeHome工程题
python -m pip install -r requirements.txt

# 跑全部示例（推荐）
python main.py --all

# 跑单个输入
python main.py example1.json

# 只要 JSON、不要 PNG
python main.py example3.json --no-viz
```

结果写到 `output/`：

- `exampleN.result.json`：是否可行 + 每个物体的中心点与旋转角  
- `exampleN.png`：轮廓 / 门禁区 / 摆放示意  

自行换输入时，JSON 字段与题目示例相同：

```json
{
  "boundary": [[x, y], "..."],
  "door": [[x1, y1], [x2, y2]],
  "isOpenInward": false,
  "algoToPlace": {
    "fridge": [1220, 1330],
    "shelf-1": [1000, 400]
  }
}
```

---

## 4. 既定输入的输出示例

四个官方示例均 **可行**，且复查通过。完整数值见 `output/*.result.json`，配图见 `output/*.png`。

### example1.json

斜墙房间、外开门、含制冰机。全部贴墙且互不重叠；冰箱开门朝室内，离地架单独占墙段。

```json
{
  "feasible": true,
  "placements": {
    "fridge":      { "center": [6456.2357, 31136.4897], "rotation": -90.0 },
    "iceMaker":    { "center": [6696.2357, 29846.4897], "rotation": -90.0 },
    "shelf-1":     { "center": [6295.9350, 28942.6597], "rotation": 179.9746 },
    "shelf-2":     { "center": [5363.1188, 29828.8439], "rotation": 105.852 },
    "shelf-3":     { "center": [4752.8941, 31977.8859], "rotation": 105.852 },
    "overShelf-1": { "center": [5089.9654, 30790.8144], "rotation": 105.852 },
    "overShelf-2": { "center": [5343.9830, 32457.0669], "rotation": 15.852 },
    "overShelf-3": { "center": [5921.1653, 32620.9590], "rotation": 15.852 }
  }
}
```

### example2.json

近矩形房间、外开门。货架与离地架分占各边，冰箱贴顶墙、开门朝室内，门洞留空。

```json
{
  "feasible": true,
  "placements": {
    "fridge":      { "center": [29766.3885, 34304.5295], "rotation": -180.0 },
    "shelf-1":     { "center": [31395.8885, 33875.6321], "rotation": 90.0 },
    "shelf-2":     { "center": [31096.3885, 34769.5295], "rotation": -180.0 },
    "shelf-3":     { "center": [29193.8885, 33005.0295], "rotation": -90.0 },
    "shelf-4":     { "center": [29493.3885, 32200.5295], "rotation": 0.0 },
    "overShelf-1": { "center": [30696.3885, 32200.5295], "rotation": 0.0 },
    "overShelf-2": { "center": [31296.3885, 32240.5295], "rotation": 0.0 },
    "overShelf-3": { "center": [31395.8885, 32940.0295], "rotation": 90.0 }
  }
}
```

### example3.json

狭长房间、**内开门**（红色 N×N 扇区）。冰箱在加宽上部，货架与离地架贴墙且互不重叠，不进入门扇。

```json
{
  "feasible": true,
  "placements": {
    "fridge":      { "center": [56563.8095, 36193.107],  "rotation": 90.0 },
    "shelf-1":     { "center": [56798.3095, 37352.606],  "rotation": 0.0 },
    "shelf-2":     { "center": [56897.8095, 34953.106],  "rotation": -90.0 },
    "shelf-3":     { "center": [56897.8095, 31953.106],  "rotation": -90.0 },
    "shelf-4":     { "center": [56897.8095, 30953.106],  "rotation": -90.0 },
    "shelf-5":     { "center": [56897.8095, 32953.106],  "rotation": -90.0 },
    "overShelf-1": { "center": [57748.3095, 37352.606],  "rotation": 0.0 },
    "overShelf-2": { "center": [57847.8095, 35773.106],  "rotation": -90.0 },
    "overShelf-3": { "center": [56897.8095, 29783.107],  "rotation": -90.0 }
  }
}
```

### example4.json

带凹槽的房间、外开门。冰箱与货架贴左墙，离地架贴顶墙/右墙，彼此不重叠。

```json
{
  "feasible": true,
  "placements": {
    "fridge":      { "center": [183539.0924, 31372.7231], "rotation": 90.0 },
    "shelf-1":     { "center": [183074.0924, 30042.7231], "rotation": 90.0 },
    "shelf-2":     { "center": [183074.0924, 32602.7231], "rotation": 90.0 },
    "overShelf-1": { "center": [183773.5924, 32902.2231], "rotation": 0.0 },
    "overShelf-2": { "center": [184373.5924, 32902.2231], "rotation": 0.0 },
    "overShelf-3": { "center": [184573.0924, 31902.7231], "rotation": -90.0 }
  }
}
```

---

## 5. 提交

将本目录上传到个人 GitHub 仓库后，把仓库链接发给招聘方即可。请勿把虚拟环境或 `__pycache__` 一并提交。
