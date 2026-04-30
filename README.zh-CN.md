# Blender GOH GEM Exporter

[English](README.md) | [中文说明](README.zh-CN.md)

`Blender GOH GEM Exporter` 是面向 `Call to Arms - Gates of Hell` / GEM 引擎资源流程的 Blender 插件。

它的目标不是简单复刻 3ds Max MultiScript，而是在 Blender 里提供更现代、更结构化的 GOH 模型、碰撞、材质、动画和物理烘焙工作流。

当前发布版本：`1.5.0`。

## 主要功能

- 导出 `mdl`、`ply`、`mtl`、`vol`、`anm`
- 导入完整 `.mdl` 模型用于查看和二次编辑
- 通过独立 humanskin 模块导入 GOH 人物 `.mdl`
- 导入 `.anm` 动画到已导入模型
- `.mdl` 导入会恢复可视 mesh、Volume、Obstacle 和 Area 辅助对象
- 支持普通模型、骨骼蒙皮模型、mesh animation 和 shape-key 网格动画
- 支持 `Volume`、`Obstacle`、`Area` 等 GOH 辅助对象
- 支持 `Box`、`Sphere`、`Cylinder` primitive volume，不必把优化用基本体碰撞强行转成网格
- 支持 `Basis` 实体元数据、旧版 Max 文本属性、Blender 结构化 `goh_*` 自定义属性
- 提供 GOH 预设、Basis 面板、Transform block、Weapon helper、Texture helper、材质自动识别和场景校验
- 导出时生成 `GOH_Export_Manifest.json`，记录文件哈希、数量统计和导出设置
- 支持 LOD 文件列表、包围盒碰撞辅助体、后坐力动作、方向射击动画、一键物理联结烘焙
- 支持从选中模型自动生成闭合、流形、全四边形碰撞 cage，使用内置 topology-first Quad Cage Fitter；车身和炮塔类大部件会自动使用沿长度采样的 Loft Cage
- `.mdl` 导入会把 EPLY 法线写入 Blender custom split normals，恢复炮管、轮子、曲面装甲等位置的原始平滑效果
- 默认 `.mdl` 导入会把 GOH 镜像 `basis` 延迟为和游戏一致的 Blender 显示空间，同时保留原始 GOH rest matrix 供导出恢复；`.anm` 导入和导出共用同一套手性补偿
- humanskin 导入会把 LOD0 skin 片段合并成一个可编辑蒙皮网格，保留权重、自定义法线和平滑，并让骨骼点位/挂点以 SOEdit 对齐方式显示

## 推荐安装

正式发布包里有两个 zip：

- `blender_goh_gem_exporter-1.5.0.zip`
  Blender 插件安装包，推荐在 Blender 里直接安装这个文件。
- `blender_goh_gem_exporter-1.5.0-full.zip`
  完整源码、文档、测试和示例素材快照，适合 GitHub 发布页或二次开发。

安装步骤：

1. 打开 Blender。
2. 进入 `Edit > Preferences > Add-ons`。
3. 点击 `Install...`。
4. 选择 `blender_goh_gem_exporter-1.5.0.zip`。
5. 启用 `GOH GEM Exporter`。

## Blender 面板

插件启用后，主要功能在 `View3D > Sidebar > GOH`：

- `GOH Presets`
  结构化预设，用来快速标记视觉模型、挂件模型、碰撞体、障碍、区域、特效点位等。
- `GOH Basis`
  代替 3ds Max MultiScript 的 `Basis` 实体模板，填写 `Type`、`Model`、`Entity Path`、`Wheelradius`、`SteerMax` 和基础动画声明。
- `GOH Tools`
  材质自动填充、验证、LOD、碰撞体生成、Transform block、Weapon / Texture helper、物理动画烘焙都在这里。
- `GOH Export`
  完整 `.mdl` 导入导出和 `.anm` 动画导入入口。

## 典型工作流

推荐从完整 `.mdl` 导入开始：

1. 使用 `Import GOH Model` 打开官方或已有模型。
2. 保持游戏一致查看推荐设置：`Axis Conversion = None / GOH Native`、`Scale Factor = 20`、`Flip V = On`、`Defer Basis Flip = On`。
3. 在 Blender 中编辑模型、材质、碰撞、辅助点位或动画。
4. 用 `GOH Presets` 或自定义属性确认对象角色。
5. 用 `Validate GOH Scene` 检查导出前常见问题。
6. 用 `Export GOH Model` 导出回 GOH / SOEdit 可读取的资源。

`Defer Basis Flip` 现在是 GOH 原生模型的默认推荐项。启用时，Blender 里显示和 SOEdit / 游戏一致的不镜像父级，但插件仍保存原始镜像 `basis` 给导出使用；导入和导出 `.anm` 时位移、旋转增量会经过同一套手性补偿，避免 Blender 与游戏内俯仰方向相反。只有在需要检查原始镜像文件空间时才关闭它。

## 动画组和 ANM

GOH 的 `.anm` 可以理解为“动画组文件”：一个文件里会记录多个对象或骨骼在同一段动画里的关键帧。

在 Blender 中，插件通过这些信息决定导出到哪个 `.anm`：

- 对象或 Action 的 `goh_sequence_name`
  GEM / MDL 里显示的动画序列名，例如 `fire`、`open`、`body_r`。
- 对象或 Action 的 `goh_sequence_file`
  实际导出的文件名，例如 `fire` 会生成 `fire.anm`。
- 多个对象使用同一个 `goh_sequence_name` / `goh_sequence_file`
  它们会被合并到同一个动画组里导出。

例如炮管是后坐力源对象，车体是物理联结对象。如果炮管写了：

```text
goh_sequence_name = fire
goh_sequence_file = fire
```

那么 `Bake Linked Recoil` 会让车体、天线等联结对象继承 `fire`，导出时会进入 `fire.anm`，不会再默认生成 `recoil.anm`。

## 物理动画烘焙

插件里的物理功能是预烘焙动画工具，不是游戏运行时实时物理。

常用功能：

- `Create Recoil Action`
  给炮管或枪管创建基础后坐力动作。
- `Assign Physics Link`
  指定源对象和被带动对象之间的物理联结。
- `Bake Linked Recoil`
  烘焙炮管后坐力带动车体、天线、挂件、履带等对象的弹簧、抖动和渐进回正。
- `Bake Directional Set`
  一次生成 `fire_front`、`fire_back`、`fire_left`、`fire_right` 等方向动画。
- `Bake Impact Response`
  生成炮弹命中后的车体晃动。
- `Create Armor Ripple`
  生成装甲波纹类 mesh animation / shape-key 变形。

调参建议：

- `Physics Power = 1.4-2.2`
  适合更有力度的坦克主炮后坐。
- `Duration Scale < 1.0`
  适合小口径、短促动作。
- `Duration Scale > 1.0`
  适合重车体回正、天线延迟摆动和更长尾部运动。
- `Body Spring`
适合车体弹簧回正，开炮后先做上仰车体摆动，然后产生多次逐渐衰减的回弹。
- `Antenna Whip`
适合天线、长杆、软连接部件。弯曲使用最小弯曲能量风格的三次弹性杆曲线，并保留较长的平滑回弹尾段。
- `Suspension Bounce` / `Track Rumble`
  适合悬挂压缩、履带和轮组震动。

## 常用自定义属性

- `goh_bone_name`
  导出的 GOH bone / part 名称。
- `goh_is_volume`
  标记对象为碰撞体。
- `goh_volume_kind`
  碰撞体类型，例如 `polyhedron`、`box`、`sphere`、`cylinder`。
- `goh_volume_bone`
  碰撞体绑定到哪个 GOH bone。
- `goh_is_obstacle`
  标记对象为 obstacle helper。
- `goh_is_area`
  标记对象为 area helper。
- `goh_sequence_name`
  动画序列名。
- `goh_sequence_file`
  动画文件名，不写时通常等于 `goh_sequence_name`。
- `goh_force_commonmesh`
  `goh_force_mesh_animation` 的兼容别名，适合习惯旧 Max `CommonMesh` 命名的工作流。
- `goh_force_mesh_animation`
  强制按 mesh animation 导出 shape-key / 网格变形。

## 兼容旧版 3ds Max 属性

插件仍然能读取旧 MultiScript 文本属性，例如：

- `Poly`
- `CommonMesh`
- `Volume`
- `ID=...`
- `Type=...`
- `Model=...`
- `Wheelradius=...`
- `SteerMax=...`
- `Animation=...`
- `AnimationResume=...`
- `AnimationAuto=...`
- `IKMin=...`
- `IKMax=...`
- `IKSpeed=...`
- `Transform=Orientation|Matrix34|Position`

优先级规则：

- Blender 结构化 `goh_*` 属性优先。
- 旧 Max 文本属性作为兼容 fallback。
- 旧 `ID=...` 可以继续驱动导出名称。

## 详细文档

- [英文详细插件手册](docs/PLUGIN_GUIDE_EN.md)
- [中文详细插件手册](docs/PLUGIN_GUIDE_ZH-CN.md)
- [快速开始](docs/QUICK_START.md)
- [物理烘焙说明](docs/PHYSICS_BAKE.md)

## 测试

仓库包含两层回归测试：

```powershell
python -X utf8 tests\smoke_test.py
```

```powershell
"D:\Steam\steamapps\common\Blender\blender.exe" -b --factory-startup --python tests\blender_runtime_test.py
```

`tests/1.blend` 是谢尔曼酱爆模型回归素材，用来辅助检查导入、坐标、动画和物理烘焙相关问题。

## 许可

本项目使用 [MIT License](LICENSE)。



