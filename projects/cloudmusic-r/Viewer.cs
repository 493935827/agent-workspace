// NeteaseUIViewer - 网易云音乐 UI 逆向查看器
// 托管解包出的 orpheus\pub 界面资源,双击运行自动打开浏览器
// 编译: csc /target:exe /out:NeteaseUIViewer.exe Viewer.cs
using System;
using System.IO;
using System.Net;
using System.Diagnostics;
using System.Threading;
using System.Text;
using System.Collections.Generic;

class Viewer
{
    static string rootDir;
    static int served = 0;

    static Dictionary<string, string> mime = new Dictionary<string, string>
    {
        {".html", "text/html; charset=utf-8"},
        {".css",  "text/css; charset=utf-8"},
        {".js",   "application/javascript; charset=utf-8"},
        {".json", "application/json; charset=utf-8"},
        {".png",  "image/png"},
        {".webp", "image/webp"},
        {".svg",  "image/svg+xml"},
        {".ico",  "image/x-icon"},
        {".cur",  "image/x-icon"},
        {".gif",  "image/gif"},
        {".jpg",  "image/jpeg"},
        {".jpeg", "image/jpeg"},
        {".wasm", "application/wasm"},
        {".woff", "font/woff"},
        {".woff2","font/woff2"},
        {".ttf",  "font/ttf"},
        {".otf",  "font/otf"},
        {".txt",  "text/plain; charset=utf-8"},
        {".bin",  "application/octet-stream"},
        {".dat",  "application/octet-stream"}
    };

    static void Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        Console.Title = "NeteaseUIViewer";

        // 定位资源目录: 参数 > EXE 同目录 orpheus\pub > CloudMusic_R\orpheus\pub
        if (args.Length > 0 && Directory.Exists(args[0]))
        {
            rootDir = Path.GetFullPath(args[0]);
        }
        else
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string candidate = Path.Combine(baseDir, "orpheus", "pub");
            if (!Directory.Exists(candidate))
                candidate = Path.Combine(baseDir, "orpheus", "orpheus", "pub");
            if (!Directory.Exists(candidate))
                candidate = @"D:\App\CloudMusic_R\orpheus\pub";
            rootDir = Directory.Exists(candidate) ? Path.GetFullPath(candidate) : null;
        }

        if (rootDir == null)
        {
            Console.WriteLine("[X] 找不到界面资源目录 orpheus\\pub");
            Console.WriteLine("    用法: NeteaseUIViewer.exe [资源目录路径]");
            Console.WriteLine("    或把本 EXE 放在 orpheus 文件夹旁边。");
            Console.WriteLine("按回车退出...");
            Console.ReadLine();
            return;
        }

        int port = 27531;
        HttpListener listener = null;
        for (; port < 27600; port++)
        {
            listener = new HttpListener();
            listener.Prefixes.Add(string.Format("http://127.0.0.1:{0}/", port));
            try { listener.Start(); break; }
            catch { listener = null; }
        }
        if (listener == null)
        {
            Console.WriteLine("[X] 27531-27599 端口均被占用");
            Console.ReadLine();
            return;
        }

        string url = string.Format("http://127.0.0.1:{0}/pub/index.html", port);
        Console.WriteLine("==============================================");
        Console.WriteLine("  网易云音乐 UI 查看器 (逆向资源静态托管)");
        Console.WriteLine("==============================================");
        Console.WriteLine("  资源目录 : " + rootDir);
        Console.WriteLine("  访问地址 : " + url);
        Console.WriteLine("  提示     : index.html(VIP收银台)可完整渲染;");
        Console.WriteLine("             app.html 为主窗口,依赖原生桥,部分内容需数据支持。");
        Console.WriteLine("  关闭本窗口即退出服务。");
        Console.WriteLine("==============================================");

        try { Process.Start(url); }
        catch { Console.WriteLine("(未能自动打开浏览器,请手动访问上方地址)"); }

        while (true)
        {
            try
            {
                HttpListenerContext ctx = listener.GetContext();
                ThreadPool.QueueUserWorkItem(delegate(object s) { Handle(ctx); });
            }
            catch (Exception ex)
            {
                Console.WriteLine("[listener] " + ex.Message);
                break;
            }
        }
    }

    static void Handle(HttpListenerContext ctx)
    {
        try
        {
            string raw = ctx.Request.Url.AbsolutePath;
            string rel = Uri.UnescapeDataString(raw);

            // 根路径跳转到入口页
            if (rel == "/" || rel == "/pub" || rel == "/pub/")
            {
                ctx.Response.StatusCode = 302;
                ctx.Response.Headers["Location"] = "/pub/index.html";
                ctx.Response.Close();
                return;
            }

            // 去掉 /pub/ 前缀映射到资源根
            if (rel.StartsWith("/pub/", StringComparison.OrdinalIgnoreCase))
                rel = rel.Substring(5);
            else
                rel = rel.TrimStart('/');

            string full = Path.GetFullPath(Path.Combine(rootDir, rel));
            if (!full.StartsWith(rootDir, StringComparison.OrdinalIgnoreCase))
            {
                Reply(ctx, 403, "403 Forbidden");
                return;
            }

            if (Directory.Exists(full))
                full = Path.Combine(full, "index.html");

            if (!File.Exists(full))
            {
                // 404 页: 列出可浏览的 HTML 入口
                StringBuilder list404 = new StringBuilder();
                list404.AppendLine("<html><head><meta charset='utf-8'><title>404</title></head><body style='font-family:sans-serif;background:#1a1a1e;color:#ddd'>");
                list404.AppendLine("<h2>404 - " + System.Web.HttpUtility.HtmlEncode(raw) + "</h2>");
                list404.AppendLine("<p>可浏览的界面入口:</p><ul>");
                string[] entries = new string[] { "index.html", "app.html", "subApp.html", "404.html", "checkdata.html" };
                foreach (string e in entries)
                {
                    if (File.Exists(Path.Combine(rootDir, e)))
                        list404.AppendLine("<li><a style='color:#6cf' href='/pub/" + e + "'>" + e + "</a></li>");
                }
                list404.AppendLine("</ul></body></html>");
                Reply(ctx, 404, list404.ToString(), "text/html; charset=utf-8");
                return;
            }

            string ext = Path.GetExtension(full).ToLowerInvariant();
            string ct;
            if (!mime.TryGetValue(ext, out ct)) ct = "application/octet-stream";

            ctx.Response.StatusCode = 200;
            ctx.Response.ContentType = ct;
            ctx.Response.Headers["Cache-Control"] = "no-cache";
            using (FileStream fs = new FileStream(full, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                ctx.Response.ContentLength64 = fs.Length;
                byte[] buf = new byte[64 * 1024];
                int n;
                while ((n = fs.Read(buf, 0, buf.Length)) > 0)
                    ctx.Response.OutputStream.Write(buf, 0, n);
            }
            ctx.Response.OutputStream.Close();
            int count = Interlocked.Increment(ref served);
            if (count % 50 == 1)
                Console.WriteLine("[ok] " + raw + "  (" + count + " reqs)");
        }
        catch (Exception ex)
        {
            try { Reply(ctx, 500, "500 " + ex.Message); } catch { }
        }
    }

    static void Reply(HttpListenerContext ctx, int code, string text)
    {
        Reply(ctx, code, text, "text/plain; charset=utf-8");
    }

    static void Reply(HttpListenerContext ctx, int code, string text, string ct)
    {
        try
        {
            ctx.Response.StatusCode = code;
            ctx.Response.ContentType = ct;
            byte[] b = System.Text.Encoding.UTF8.GetBytes(text);
            ctx.Response.ContentLength64 = b.Length;
            ctx.Response.OutputStream.Write(b, 0, b.Length);
            ctx.Response.OutputStream.Close();
        }
        catch { }
    }
}
