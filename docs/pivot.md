# 静态资产原点

```sh
openfigura pivot /absolute/task/path --mode ground --artifact model.glb
```

`ground`把脚底/模型最低点放在glTF Y=0，水平包围盒中心放在X/Z=0；`center`
把实际包围盒中心放在原点。范围是默认场景里被三角形引用的位置顶点，计算节点
matrix/TRS/父层级变换，不相信陈旧的accessor min/max。

新资产根为identity，可绕新的脚底/中心旋转；其平移子节点包装原有场景根。
原nodes、mesh、UV、法线、材质、图像和BIN字节保持不变。世界位置会平移，
不是把模型留在旧世界坐标。报告记录位移、前后bounds、根节点ID和hash。

当前支持单场景静态嵌入GLB、indexed triangles、FLOAT VEC3位置；拒绝skin/
animation/morph/instancing/压缩或外部buffer、不支持的扩展和外部图像sidecar。
在autorig前使用；已有动作资产需要另做受控的骨架变换支持。

`figura_pivot`、CLI和`execute`的pivot步骤共用engine。原输入为私有副本，发布
GLB及report均防覆盖；失败只隔离本次拥有的文件，竞争者文件保留。成功前核对
身份和hash，阶段输出也复核，防止把竞争替换后的文件登记为pass。

真实证据`.local/runs/2026-10-09-studio-pivot-tool/`：CLI ground、MCP center、
execute ground、原BIN/属性/旧nodes完整比对和实际Blender正面帧通过。测试脚本
首轮取错stage_result，已用原产物continuation验证，再以新tasks-review重验。
旧任务和失败记录未重置。美术接受仍pending；此工具不修复白眼/口袋或碰撞。
