# 云端上传经验

验证日期：2026-10-27（北京时间）。

## COS

此前环境通过配置的 http://proxy:8080，使用 curl -X PUT -T 上传云端运行环境中的测试文件到 gpt/hello.md，COS 返回 HTTP 200。

- 执行沙箱可能阻止网络连接：socket 返回 Operation not permitted，curl 可能显示无法连接代理。此时不能直接判断代理服务故障，应使用平台允许的沙箱外执行机制验证。
- 当时沙箱外 proxy:8080 可连接；proxy:7987 返回 Connection refused。
- 当时 --noproxy '*' 直连无法解析公网域名。保留环境配置的代理和 CA 信任。
- -T 路径是执行 curl 的云端环境中的文件，不需要用户电脑文件。
- 预签名链接必须使用生成时的 HTTP 方法、对象路径和有效期；不要单独修改签名参数。文档不保存完整预签名链接或凭据。
- 这些结果来自当时环境，新环境需重新检查。

示例（COS_PRESIGNED_URL 由用户提供）：

```bash
curl --proxy http://proxy:8080 --connect-timeout 15 --max-time 45 \
  -X PUT -T /path/to/cloud-file.md "$COS_PRESIGNED_URL"
```

## GitHub

本次环境通过默认代理访问 GitHub API，仓库 shaochun321/TheLiying-cloudtest 返回 HTTP 200，权限包含 push=true。

实际上传验证使用独立测试分支中的此文档，不修改 main、不触发部署操作。实际结果以聊天中的 API 返回结果为准。

凭据从运行时配置的 GH_TOKEN 使用，不打印、不写入文档或仓库。保留代理、证书配置。网络访问成功不代表所有仓库或所有操作都有权限。

## 排查顺序

1. 检查环境网络策略和凭据就绪状态。
2. 检查代理地址、DNS 和 TCP 连接，区分沙箱拒绝、端口拒绝连接及 DNS 失败。
3. 必要时按平台审批机制在沙箱外复核，不能以更换端口或关闭代理代替诊断。
4. 检查实际 HTTP 状态和服务端响应；curl 退出成功不必然表示 HTTP 成功。
5. 只记录已验证的结论，并在新环境重新验证。
