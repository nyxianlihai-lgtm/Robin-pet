# 将 Robin-pet v1.0 上传到 GitHub

项目仓库：https://github.com/nyxianlihai-lgtm/Robin-pet 。以下保留首次上传与版本标签的操作说明。

## 1. 创建空仓库

登录 https://github.com/new ，仓库名填 `Robin-pet`。描述可填：

> Windows 知更鸟同人 AI 桌宠，支持透明动画、桌面互动、DeepSeek 聊天和本地语音。

按需要选择 Public（公开）或 Private（私有）。首次上传已有本地项目时，不勾选创建 README、.gitignore 或许可证，以免新仓库自带提交与本地历史冲突。代码许可证以后确定后再添加；项目内保留同人、非官方及素材来源说明。

## 2. 在终端中提交

注意：PowerShell 切换目录用 `Set-Location 'E:\Codex\create-pet'`；CMD 则必须用 `cd /d E:\Codex\create-pet` 才能从 C 盘切到 E 盘。不要在 `C:\Users\用户名` 执行 `git init` 或 `git add .`。下面用 `git -C` 指定绝对路径，在两种终端中都不会选错目录。

本机已可使用 Git。先在项目目录执行：

```powershell
git -C "E:\Codex\create-pet" init -b main
git -C "E:\Codex\create-pet" add .
git -C "E:\Codex\create-pet" status --short
git -C "E:\Codex\create-pet" diff --cached --stat
```

确认暂存列表不包含 `.venv/`、`data/`、`qa/` 或 `.env` 文件后，再提交：

```powershell
git -C "E:\Codex\create-pet" commit -m "Release Robin-pet v1.0"
```

如果 Git 提示没有提交身份，先配置本仓库的身份，再重试 commit（将示例替换成你自己的名字和邮箱，可用 GitHub 设置里的 noreply 邮箱）：

```powershell
git -C "E:\Codex\create-pet" config user.name "你的 GitHub 用户名"
git -C "E:\Codex\create-pet" config user.email "你的提交邮箱"
```

`data/settings.json` 包含个人接口设置和加密后的 API Key，整个 `data/` 已忽略。`.venv/`、缓存、检查录像和过时的 HQ WebP 中间帧也已忽略。默认仍包含参考视频、角色方案、旧版本素材和代码，方便保留制作过程；当前运行所需的是代码、批处理、`requirements.txt`、`assets/robin.png` 以及 `assets/video2_hq/manifest.json` 和其中 PNG 帧。

## 3. 关联仓库并推送

把下面的 `YOUR_USERNAME` 替换成仓库所属 GitHub 用户名：

```powershell
git -C "E:\Codex\create-pet" remote add origin https://github.com/YOUR_USERNAME/Robin-pet.git
git -C "E:\Codex\create-pet" push -u origin main
git -C "E:\Codex\create-pet" tag -a v1.0 -m "Robin-pet v1.0"
git -C "E:\Codex\create-pet" push origin v1.0
```

首次连接按 Git 凭据管理器或浏览器提示完成登录。不要把账号密码或访问令牌写进项目、远程 URL 或发到聊天中。

上传后刷新仓库页面，检查 README、代码和 PNG 素材是否可见。当前是源码项目，其他人克隆后需安装 Python，运行 `setup.bat`，再运行 `启动桌宠.bat`；尚未打包成独立 EXE。

## 4. 创建版本页面（可选）

打开仓库 Releases，创建 release，选择已有标签 `v1.0`，标题 `Robin-pet v1.0`。说明可写：

```text
Robin-pet v1.0 初始版本

- 学院换装透明视频角色，适配高 DPI。
- 待机眨眼、立即抬手互动、转身、向左散步。
- DeepSeek 兼容聊天接口和 Windows 本地语音。
- 暂不支持向右走路、角色原声或麦克风输入。

Windows 源码版：安装 Python 后运行 setup.bat，再运行启动桌宠.bat。
个人同人项目，非游戏官方应用。
```

当前 PNG 帧合计约 192 MiB；不建议用网页逐个上传。当前已检查的资产中没有超过 GitHub 普通 Git 单文件 100 MiB 限制的文件，首次可直接使用 Git 推送。以后素材包显著增大，可考虑 Git LFS 或 Release 附件。

官方参考：

- https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github
- https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
