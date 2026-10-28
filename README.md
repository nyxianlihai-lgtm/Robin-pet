# Robin-pet v1.0

> 本项目是作者自制的非官方、非商业同人桌宠与开源技术实践，不是游戏官方应用。角色同人形象、换装及动作由作者自行策划、制作和整理，制作过程包含 AI 辅助生成；本项目与原作运营方不存在合作、赞助或背书关系。
>
> © 米哈游版权所有。
>
> 《崩坏：星穹铁道》素材的权利归米哈游所有，其他内容的相关权利、利益均归各自所有者享有。
>
> 收到相关权利人的通知即删除或下架对应内容。代码和素材分别适用下述使用条款。

Windows 桌宠程序，支持拖动、置顶、透明视频播放、DeepSeek 兼容接口聊天和 Windows 本地朗读。

<img src="assets/video2_hq/frames/frame_0363.png" alt="随附同人角色示意" width="160">

本版本恢复随附人物图片和完整运行帧包：`assets/robin.png`、`assets/video2_hq/manifest.json` 及 484 张透明 PNG 帧。完整克隆或下载仓库后即可显示人物和播放动作，无需自己制作视频。参考视频、参考图片和创作过程归档不随仓库分发。

## 运行

安装 Windows 版 Python 3.10 或以上，完整克隆或下载仓库，运行 `setup.bat` 安装依赖，再运行 `启动桌宠.bat`。默认加载随附人物动画。首次启动会打开陪伴面板。关闭面板只隐藏窗口，退出请使用托盘或右键菜单。请勿只复制 Python 文件，需一并保留 `assets/`。这是 Windows 桌面程序，不是网页服务。

## 用自己的视频制作可选帧包

准备自己制作、持有相关使用权且符合适用规则的视频。建议固定镜头、纯绿色背景、完整人物，各动作保持相同画布和角色大小。工具只进行通用抠像和帧整理，不生成角色，不主动移除文字或标识。

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-tools.txt
.venv\Scripts\python.exe tools/prepare_video2.py --input "你自己的待机视频.mp4"
```

自定义素材默认输出 `data/pet-assets/manifest.json` 和透明 PNG 帧，重启桌宠即可优先加载；没有自定义帧包时加载仓库随附的 `assets/video2_hq/`。`data/` 已被 Git 忽略。重复生成同一位置需显式加 `--replace`，使用其他位置可设置进程环境变量 `ROBIN_PET_ASSETS`。不需要自定义角色时，可跳过这一节。

可选输入：`--wave` 招呼、`--turn` 完整转身再返回、`--walk-in` 转向、`--walk` 向左迈步循环、`--walk-out` 停步转回正面。走路三项需一起提供；缺少的动作不会播放。视频需保持相同画布和角色锚点，衔接姿态由自己的视频决定。待机使用真实帧往返循环，其他动作正向播放。

可用 `--wave-start 1.5` 等参数裁去对应视频开头的静止段，单位秒；`--fps` 调整输出帧率，默认 24fps；绿色眼睛可试用 `--protect-eyes` 并自行检查结果。绿色服饰不适合绿幕抠像。完整参数见 `--help`，格式示例见 `assets/manifest.example.json`。

精修抠像后可直接提供包含透明 PNG 序列的文件夹，使用补零文件名（例如 `frame_0001.png`）。工具保留其颜色和 alpha，不再进行绿幕抠像。`--sequence-fps` 指定 PNG 原始帧率，默认 24；自然闭环的待机添加 `--idle-loop forward`，避免倒放。各动作参数均支持视频或 PNG 序列目录。

```powershell
.venv\Scripts\python.exe tools/prepare_video2.py --input "你的透明待机帧目录" --idle-loop forward --sequence-fps 24
```

走路组可加 `--walk-stride 120`，表示每圈步态的地面位移为 120 个源图像像素；数值须按自己的步态测量。高级帧包可在 `walk` 中提供 `travel_curve`：长度为走路帧数加一、从 0 到 1 非递减的累计位移数组，表示每个帧边界的地面位移进度。缺少实测数据时保留原有匀速兼容行为。

## 互动和聊天

- 拖动移动角色，双击打开聊天，右键提供动作和显示设置。
- 手动动作立即切换，约 0.12 秒整帧过渡，结束后恢复待机；暂停保持当前帧。
- 连续摸摸保持当前招呼动作的进度；菜单中的动作预览可以重新播放。返回待机时选择更接近当前姿态的帧，片段之间也提供短暂过渡。
- 帧包包含完整走路组时可散步，窗口只在实际迈步片段中移动。目前按向左走路处理。
- 设置可调整大小、置顶、散步及自动朗读，显示适配高 DPI。
- `动作预览.bat` 用于检查已生成帧包的透明边缘。

在模型设置中填入自己的 API Key 和兼容接口。聊天时最近最多 10 轮对话和角色设定会发给所配置的服务商，费用以服务商为准。对话仅保留在内存，退出清空。

配置保存在 `data/settings.json`，API Key 使用 Windows DPAPI 加密，绑定当前用户；个人配置、虚拟环境和检查输出不提交到仓库。语音采用 Windows 本地朗读，不包含角色原声、音色克隆或麦克风输入。程序不连接或修改游戏，不提供游戏插件或私服功能。

## 动画方法来源与后续优化

本项目的桌宠制作参考了 [MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop)，尤其是其 [动画素材流水线](https://github.com/MerZlin/dsh-pet-indesktop/blob/34d810b1eadd98d00e7cb9b3b51428a45b5bf03e/docs/ASSET-PIPELINE.md) 中的动作首尾闭环、固定构图、脚底锚点与透明素材处理方法。该文档说明，其素材制作流程承接自 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)。感谢两项目作者的开源分享。

Robin-pet 当前使用透明 PNG 帧包；上述项目采用的透明 WebM 流程和步态同步方法将作为后续优化参考。具体来源、当前差异、5 秒视频制作要求及验收计划见 [动画制作与优化方案](docs/ANIMATION_PIPELINE.md)。本段说明技术方法的参考来源；角色素材的来源和使用条件见下文及 [ASSETS.md](ASSETS.md)。

## 代码与素材

代码、通用工具和纯几何示意图采用 [MIT](LICENSE)。项目的非商业同人定位不改变 MIT 对代码的使用范围。

随附的作者同人角色素材不随代码许可，不可商用、不可再分发，详见 [ASSETS.md](ASSETS.md)。自备素材的权利归属和适用条件由原有规则决定。

## 检查

```powershell
.venv\Scripts\python.exe verify.py
.venv\Scripts\python.exe verify_bundled.py
.venv\Scripts\python.exe -m pip install -r requirements-tools.txt
.venv\Scripts\python.exe verify_video.py
```

界面检查使用本地模拟服务；视频检查使用临时生成的几何图形测试片，不需要角色素材。临时检查文件保存在被忽略的目录中。

本仓库曾清理参考素材历史，本次按维护者要求恢复部署必需的人物图片和运行帧包；参考视频和参考图片仍被 Git 忽略。此前下载过不含人物的源码版本，请更新 main 或重新下载 v1.0，并从托盘退出旧实例后重启。
