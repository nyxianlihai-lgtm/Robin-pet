# Robin-pet 仓库维护

仓库：https://github.com/nyxianlihai-lgtm/Robin-pet

当前仓库包含通用代码、MIT 许可、素材使用说明，以及部署必需的人物图片和 `assets/video2_hq/` 透明 PNG 帧包。参考图片、原始视频、过时帧包和创作过程归档仍保留本地，不上传；具体边界见 ASSETS.md。

## 后续更新

```powershell
git -C "E:\Codex\create-pet" add .
git -C "E:\Codex\create-pet" diff --cached --stat
git -C "E:\Codex\create-pet" commit -m "Describe the change"
git -C "E:\Codex\create-pet" push
```

提交前确认不包含 data、个人 API 配置、参考图、原始视频或过时帧包。默认人物的 PNG 帧包已在 Git 忽略规则中明确放行，不能漏传。其他自备素材放在 data/pet-assets 或 user-assets。不要使用强制 add 绕过参考素材的排除规则。

## 历史清理后

main 和 v1.0 的参考素材历史曾通过 git-filter-repo 重写。本次按维护者要求恢复人物图片和运行帧包，参考视频和参考图片仍不分发。清理前的备份只保存在本地 data/history-before-cleanup.git，不应上传。

发布的源码版本需完整包含当前受 Git 跟踪的运行帧包，避免用户只下载代码后看不到人物。勿附加原始参考视频或参考图片。若遇到权利反馈，通过相关联系渠道处理。

GitHub 的旧 SHA 缓存、其他人的 fork 和已下载副本可能仍保留历史内容；普通强推无法回收这些副本。
