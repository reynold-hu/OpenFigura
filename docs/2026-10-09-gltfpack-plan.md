# 属性约束简化：已授权优化迁移的实施计划

用户已批准技术栈迁移与完整Studio能力，当前执行现有optimize项，不改变产品定位。
源高模存在薄层和相反绕序UV面，强行成单实体会损失信息。本路线直接在原始
GLB上使用独立MIT meshoptimizer工具，避免再叠加删面或BMesh重写。

对比已做：raw Decimate破坏接缝；精确合并改善外观但有新重复面；MeshLab删面
消除非流形边却增加开放边界/碎片。选属性/边界约束gltfpack作独立可选backend，
保留原Blender工具，不把它当全模型repair或水密证明。

1. 外部官方原生ARM64工具，固定版本/下载hash/LICENSE/help，core不引新依赖。
2. 单次保守原始高模试验：无量化、锁边界、保留名字/材质/extras，禁止激进模式。
   目标ratio与实际值分开，不为达面数预算破坏结构。
3. 核对纹理字节/材质引用、变换、几何精确位置拓扑、实际material/clay帧。
   有回归则诊断拒绝；不能仅凭CLI exit0通过。
4. 通过试验后实现可选backend，engine/CLI/MCP/execute统一路由，原始输入快照
   不变；参数、失败隔离、缓存身份与报告有单元测试和独立复审。
5. 真实API产物与渲染通过技术验收后，再做该新资产的MIA和独立动作闸。
   不复用旧失败动作冒充新结果，2mm接触阈值及有限采样限制保持。

任何视觉接受仍pending；原始白眼/口袋错误要另走材质/形状优化，简化器不会修复。

## 实测结论：暂不注册简化后端

官方v1.3原生ARM64工具已安装验证，MIT许可；外部runtime不进入core。
原配置947,962→87,494面，但非流形边2570→3263、重复面322→926，拒绝。
核对官方代码后发现不加`-sv`时UV误差权重为0；仅接缝约束，不称完整UV优化。
补文档明确的`-sv`做一次新假设测试：87,418面，非流形边3257、重复面930，
仍拒绝。两者边界0、图像payload和nodes未变；root看了真实clay/frame，仍有
局部瑕疵和细节损失，未通过原拓扑质量门禁。无ratio网格搜索、无阈值调整。
产物分别为`.local/runs/2026-10-09-gltfpack-trial/`和`gltfpack-visual-attributes/`。

依据：[官方glTFpack说明](https://github.com/zeux/meshoptimizer/blob/v1.3/gltf/README.md)、
[官方算法实现](https://github.com/zeux/meshoptimizer/blob/v1.3/gltf/mesh.cpp)。
