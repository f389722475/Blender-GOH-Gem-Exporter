# GOH Blender 插件详细指导手册

这份手册讲的是如何用插件在 Blender 里搭建一辆 GOH 车辆，重点是车体、炮塔、炮管、履带、碰撞体、辅助点、动画和导出。

最重要的一句话：GOH 车辆不是单纯一个 mesh，而是一棵有名字、有父子层级、有 pivot、有辅助体、有动画片段的 transform 树。

在 Blender 里，通常不需要给普通坦克强行做 Armature。绝大多数车辆可以用普通 Object 层级来搭：

- `Body` 是车体主根。
- `Turret` 挂在 `Body` 下面。
- `Gun`、`Gun_rot` 或炮盾挂在 `Turret` 下面。
- 炮口、瞄准点、抛壳点等 helper 挂在炮管或火炮组件下面。
- 履带、车轮、悬挂 helper、履带碰撞体挂在 `Body` 下面。

对象的 Origin 就是旋转/移动 pivot。这是 rigging 里最容易出问题、也最重要的规则。

如果炮塔绕着车体外面转，说明炮塔 Origin 不在炮塔座圈中心。如果炮管俯仰点不对，说明 `Gun_rot`、炮盾或炮管对象的 Origin 没放在耳轴/俯仰轴上。

## 1. 推荐起步流程

尽量先导入一个官方模型当参考。

1. 打开 Blender。
2. 使用 `GOH Export > Import GOH Model`。
3. 导入一个和目标载具相似的官方 `.mdl`。
4. 常规编辑建议使用：
   - `Axis Conversion = None / GOH Native`
   - `Scale Factor = 20`
   - `Defer Basis Flip = On`
   - `Import Volumes = On`
   - `LOD0 Only = On`，快速查看时打开即可
5. 在 Outliner 里观察官方模型层级。
6. 重点看这些名字：
   - `body`
   - `root`
   - `turret`
   - `gun`
   - `gun_rot`
   - `track_l`
   - `track_r`
   - `wheel`
   - 以及 `_vol` 结尾的碰撞体

不要直接照搬官方资产内容，但可以学习它的结构：父子关系、pivot 位置、helper 命名、碰撞体风格。

## 2. 场景基础设置

### Basis

打开 `View3D > Sidebar > GOH > GOH Basis`。

启用 Basis metadata，然后填写：

- `Vehicle Name`
- `Type`
- `Entity Path`
- `Wheelradius`
- `SteerMax`

然后运行：

- `Copy Legacy Text`：需要旧 Max 文本属性时使用。
- `Sync Basis Helper`：创建或更新隐藏的 `Basis` helper。

`Basis` 用来保存模型级别元数据。它应该在场景原点，保持位置、旋转、缩放为默认值。

### 缩放和坐标

推荐导出设置：

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`

最终导出前建议：

- 尽量应用 visual mesh 的缩放。
- 避免负缩放。
- 保持每个运动部件的 Origin 有意义。
- 导出前一定跑 `Validate GOH Scene`。

## 3. 推荐层级

一个简单坦克可以按这个思路搭：

```text
Basis
Body
  TrackL
  TrackR
  WheelL_01
  WheelR_01
  Turret
    Mantled
    Gun_rot
      Gun
        Foresight3
        FxShell
```

导入官方模型时也可能看到这种名字：

```text
vehicle#x_root_101
  vehicle#bone_turret_58
    vehicle#bone_gun_66
      vehicle#bone_gun_barrel_67
```

这两种都可以。Blender 对象名和最终 GOH bone 名不一定完全相同，关键是 `goh_bone_name` 属性要正确。

## 4. 使用 GOH Presets

打开 `View3D > Sidebar > GOH > GOH Presets`。

重要选项：

- `Template Family`
  普通履带载具用 `Tank`。
- `Role`
  选择对象类型：
  - `visual`
  - `volume`
  - `attachment`
  - `obstacle`
  - `area`
- `Part`
  选择具体部件，比如 `Body`、`Turret`、`Gun`、`TrackL`、`TrackR`、`Foresight3`、`FxShell`。
- `Rename Objects`
  把 Blender 对象重命名为预设名。
- `Write Export Names`
  写入 `goh_bone_name` 等导出属性。
- `Auto Number`
  适合座位、乘员点、车轮、特效点等重复 helper。
- `Helper Collections`
  自动把 helper 放进 GOH 专用 collection。

典型用法：

1. 选中车体 mesh。
2. `Role = visual`。
3. `Part = Body`。
4. 打开 `Write Export Names`。
5. 点击 `Apply GOH Preset`。

炮塔、炮管、履带、车轮、碰撞体、辅助点都按这个逻辑处理。

## 5. 车体 Body 设置

车体是车辆主根。

推荐设置：

- 名称或导出名：`body`，或者沿用导入模型的 root 名称。
- 父级：通常没有父级，或者按你的工程需要挂在 `Basis` 下。
- Origin：车体中心附近，或者保持官方导入 root 的 pivot。
- Preset：`visual > Body`。

车体下面通常包括：

- 车体 mesh
- 履带 mesh
- 车轮 mesh
- 炮塔对象
- 绑定到 `body` 的碰撞体
- obstacle / selection helper
- area helper

普通坦克里，车体一般保持稳定，炮塔和炮管相对车体运动。

## 6. 炮塔 Turret 设置

炮塔最关键的是 yaw pivot，也就是水平旋转中心。

推荐设置：

- 父级：`Body`
- Origin：炮塔座圈中心
- Preset：`visual > Turret`
- `goh_bone_name`：通常是 `turret`

步骤：

1. 选中炮塔 mesh。
2. 把对象 Origin 移到炮塔座圈中心。
3. 保持 transform 的情况下，把炮塔 parent 到车体。
4. 应用 `GOH Presets > visual > Turret`。
5. 把炮塔上的部件 parent 到炮塔：
   - 炮盾
   - 火炮俯仰 pivot
   - 炮管
   - 同轴机枪
   - 炮塔舱盖
   - commander / gunner helper
   - 炮塔碰撞体

测试方法：

1. 第 1 帧给炮塔 rotation 插入 keyframe。
2. 绕本地垂直/yaw 轴旋转炮塔。
3. 再插入 keyframe。
4. 拖动时间轴查看。

如果炮塔绕车体外面转，而不是原地旋转，说明 Origin 错了。

## 7. 火炮和炮管 Gun 设置

火炮组件通常有两种运动：

- 围绕耳轴/俯仰 pivot 上下俯仰
- 沿炮管方向后坐

推荐层级：

```text
Turret
  Gun_rot
    Gun
      Gun_barrel
      Foresight3
      FxShell
```

也可以是：

```text
Turret
  Mantled
    Gun
      Gun_barrel
```

推荐设置：

- `Gun_rot` 或 `Mantled` 的 Origin 放在火炮俯仰轴/耳轴。
- `Gun` 或炮管可以和俯仰 pivot 共用 Origin，也可以有自己的 mesh 中心。如果要在炮管对象上烘焙后坐，注意后坐方向要正确。
- 炮口、瞄准点、抛壳点如果要跟着后坐，就 parent 到会后坐的炮管/火炮对象。
- 固定在炮盾上的装甲，如果会跟着火炮俯仰，就 parent 到俯仰 pivot。

常用预设：

- 主炮 mesh：`visual > Gun`
- 火炮俯仰 pivot：`visual > Gun_rot`
- 机枪 mesh：`visual > Mgun`
- 机枪 pivot：`visual > Mgun_rot`
- 炮盾：`visual > Mantled`
- 炮口/瞄准 helper：`attachment > Foresight3`
- 抛壳 helper：`attachment > FxShell`
- 手柄 helper：`attachment > Handle`

Weapon helper 快捷按钮：

- `CommonMesh`
  标记为需要 mesh animation 采样的对象。
- `Poly`
  标记为旧式 visual poly 部件。
- `Foresight3`
  标记炮口/瞄准参考点。
- `FxShell`
  标记抛壳/弹壳 helper。
- `Handle`
  标记 handle helper。

## 8. 炮管后坐 Recoil

打开 `GOH Tools > Physics Bake Presets`。

简单后坐：

1. 选中炮管或火炮对象。
2. 设置 `Recoil Axis`。
3. 选择在 Blender 里能让炮管向后移动的轴。
   - `Local -Y` 是常见起点。
   - 如果炮管向前跑，就换成相反轴。
4. 设置 `Distance`。
5. 设置 `Frames`。
6. 打开 `Write Sequence`。
7. 设置 `Clip Prefix`，通常用 `fire`。
8. 点击 `Create Recoil Action`。

联动后坐：

1. 先选源对象，比如主炮。
2. 再选车体、天线、悬挂、履带、外挂物等被带动对象。
3. 确保主炮是 active object。
4. 选择 `Link Role`。
5. 点击 `Assign Physics Link`。
6. 点击 `Bake Linked Recoil`。

常用 Link Role：

- `Body Spring`
  主炮开火时车体弹簧反应。
- `Antenna Whip`
  天线柔性甩动。
- `Accessory Jitter`
  工具箱、外挂物、杂物震动。
- `Suspension Bounce`
  车体和悬挂弹跳。
- `Track Rumble`
  履带、车轮、负重轮快速小幅震动。

## 9. 履带和车轮 Tracks / Wheels

履带通常分三部分处理：

- visual mesh
- 车轮/悬挂 helper 层级
- 碰撞体和 obstacle helper

### 履带 visual

推荐设置：

- 左履带：
  - preset 用 `visual > TrackL` 或 `visual > Track`
  - parent 到 `Body`
- 右履带：
  - preset 用 `visual > TrackR` 或 `visual > Track`
  - parent 到 `Body`

如果履带 mesh 使用 shape key 或逐帧 mesh 变形：

- 在 `GOH Presets` 里把 mesh animation mode 设为 `Force`，或者
- 使用 `CommonMesh` 快捷按钮。

很多 GOH 履带运动来自 vehicle/entity 配置，不完全是在 Blender 里做的。插件负责导出几何、层级、helper 和预烘焙动画，不会自动替代所有游戏运行时车辆逻辑。

### 车轮和悬挂

常用 visual / attachment 预设：

- `Wheel`
- `Wheell`
- `Wheelr`
- `TrackL`
- `TrackR`
- `SteerL`
- `SteerR`
- `SpringL`
- `SpringR`
- `WheelsL`
- `WheelsR`
- `WheelSL`
- `WheelSR`

建议：

- 车轮 mesh 通常 parent 到 `Body`，如果有独立悬挂 parent，就挂到对应 parent。
- 车轮 Origin 放在轮心。
- 左右命名保持一致。
- 车轮 dummy 和悬挂 helper 的位置最好参考官方导入模型。

### 履带碰撞体

碰撞体可以这样做：

- 使用 volume 预设 `TrackL` 和 `TrackR`。
- 或者选中履带 mesh，运行 `Auto Collision Cage Volume`。

推荐设置：

- `Face Budget = 200-500`
- `Optimize Iterations = 8-16`
- `Cage Template = Auto` 或 `Rounded Box`
- `Output Topology = Tri / Quad Legal`
- `Clear Previous = On`

履带这种长条结构，很多时候简单 box / rounded box 碰撞体比非常贴合的复杂 cage 更稳定。碰撞体不需要看起来和 visual mesh 一模一样，稳定、封闭、可读更重要。

## 10. 碰撞体 Collision Volumes

GOH 碰撞体通常是 `_vol` 结尾的 mesh，或者带 GOH volume 属性的对象。

重要属性：

- `goh_is_volume = True`
- `goh_volume_name`
- `goh_volume_bone`
- `goh_volume_kind`

常见 volume kind：

- `polyhedron`
- `box`
- `sphere`
- `cylinder`

### Auto Collision Cage Volume

打开 `GOH Tools > Collision Helpers`。

推荐起步参数：

- `Cage Template = Auto`
- `Fit Mode = OBB Only`
- `Cage Source = Selected`，适合单独精修
- `Cage Source = Selected + Children`，适合选择 root 后批量生成
- `Output Topology = Tri / Quad Legal`
- `Face Budget = 500`
- `Optimize Iterations = 8-16`
- `Offset = 0.005`
- `Use Modifiers = On`
- `Clear Previous = On`

如果是单个精修部件：

- `Face Budget` 可以提高到 `1000-5000`
- `Optimize Iterations` 可以提高到 `20-40`

如果是整车：

- 迭代次数不要太高。
- 尽量少选源对象。
- 最好手动分成车体、炮塔、炮管、履带几组生成。

## 11. LOD 设置

打开 `GOH Tools > LOD Helpers`。

常规流程：

1. 选中 visual mesh。
2. 设置 `LOD Levels`。
3. 如果最后一级要消失，打开 `Write OFF`。
4. 点击 `Assign LOD Files`。

插件会写入类似这样的 `goh_lod_files`：

```text
body.ply;body_lod1.ply
```

LOD 命名尽量稳定，导出后查看 manifest。

## 12. 动画片段和 Sequence

插件会从 Blender Action 和记录的 clip range 导出动画。

常用属性：

- `goh_sequence_name`
- `goh_sequence_file`
- `goh_sequence_ranges`

简单情况：

```text
goh_sequence_name = fire
goh_sequence_file = fire
```

多片段情况：

```text
goh_sequence_ranges = fire:1-48; hit_body:49-96
```

常见片段：

- `fire`
- `fire_front`
- `fire_back`
- `fire_left`
- `fire_right`
- `fire_fl`
- `fire_bl`
- `fire_br`
- `fire_fr`
- `hit`
- `open`
- `close`

开火触发体可以用 `Create Fire Trigger Volumes` 一键生成：在 `basis` 下创建 `recoil_gun_*_vol` 圆饼扇形 volume，在 `turret` 下创建或复用 `gun_recoil` 点位。四方向把 `front/back/left/right` 对齐到 `+X/-X/+Y/-Y`；八方向额外生成 `fl/bl/br/fr`。

## 13. 导出

导出前：

1. 运行 `Validate GOH Scene`。
2. 先修 Error。
3. 再查看 Warning。
4. 保存 `.blend`。
5. 打开 `GOH Export`。
6. 导出 `.mdl`。

推荐导出设置：

- `Axis Conversion = None / GOH Native`
- `Scale Factor = 20`
- `Flip V = On`

导出后检查：

- `.mdl`
- `.ply`
- `.vol`
- `.anm`
- `GOH_Export_Manifest.json`
- `GOH_Validation_Report.txt`

## 14. 常见问题

### 炮塔绕错位置旋转

修炮塔对象 Origin。Origin 必须在炮塔座圈/yaw pivot。

### 炮管俯仰点错误

修 `Gun_rot`、炮盾或炮管对象 Origin。Origin 必须在耳轴/俯仰轴。

### 炮管后坐方向反了

把 `Recoil Axis` 改成相反的 local axis。

### 炮口 helper 不跟随炮管

把 `Foresight3`、炮口点或 `FxShell` parent 到真正会后坐的炮管/火炮对象。

### 履带导出了但游戏里不动

确认这部分运动是不是应该来自 game-side vehicle 配置。插件负责导出 mesh、helper 和预烘焙动画，不会自动生成所有运行时车辆逻辑。

### 碰撞体太复杂

降低：

- `Face Budget`
- `Optimize Iterations`
- 选中的源对象数量

### 碰撞体太大

使用：

- `Cage Source = Selected`
- 只选车体或炮塔本体
- `Cage Template = Rounded Box`
- `Optimize Iterations = 8-16`
- 更小的 `Offset`

### 导出的动画方向镜像了

导入 GOH 原生模型时，如果目标是和 SOEdit / 游戏内 helper 点位、子物体方向一致，保持 `Defer Basis Flip = On`。插件会在 Blender 中显示游戏一致的不镜像父级，同时保存原始镜像 `basis` 供导出恢复；只有在需要检查原始镜像文件空间时才手动关闭。默认显示模式下 `.anm` 导入和导出都会走同一套手性补偿。

## 15. 出包前检查清单

导出一辆车前建议逐项确认：

- 车体导出名正确。
- 炮塔 parent 到车体。
- 炮塔 Origin 在水平旋转中心。
- 火炮俯仰 pivot 正确。
- 炮管、炮口 helper、抛壳 helper parent 正确。
- 履带和车轮 parent 到车体或正确悬挂 parent。
- 碰撞体绑定到正确的 `goh_volume_bone`。
- `_vol` helper 没有被当成 visual mesh 误导出。
- LOD file list 已写好。
- 材质有 GOH texture 字段。
- Basis helper 已同步。
- Validation report 没有 Error。
