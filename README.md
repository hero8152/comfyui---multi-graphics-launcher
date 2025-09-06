多张显卡使用便携版的bat启动会存在很多的管理问题，例如：1. 只能重启软件而无法在webui中关闭bat进程。 2. 多张显卡需要在多个网页端口切换，无法在一个窗口中管理所有显卡。 3. bat有时候会卡死，如果是在服务器电脑中，需要登陆进去关闭bat后重新运行。 4. 多显卡需要运行多个bat窗口。

我不会写代码，这是我用deepseek一点点的优化改进的代码，亮点是：

只需要运行一个进程，可以在一个网页中自由的对双显卡进行单独控制 开启/关闭/重启 等功能。
控制器可以随意挪动摆放
因为是用的反向代理功能，例如我的显卡用的是5090和4090端口启动，通过反向代理到8000端口来集中控制，也可以通过5090和4090的端口单独打开原始网页，功能上并不会干扰到现有代码。
这些是功能截图：

------------翻译/translate-----

There are many management problems when using the portable version of BAT boot for multiple graphics cards, such as: 1. Only the software can be restarted without closing the bat process in webui. 2. Multiple graphics cards need to be switched on multiple web ports, and it is not possible to manage all graphics cards in one window. 3. bat sometimes freezes, if it is in the server computer, you need to log in to close the bat and run it again. 4. Multi-graphics cards need to run multiple BAT windows.

I don't know how to write code, here is the code that I improved with a little bit of optimization with deepseek, the highlights are:

Only need to run a process, and you can freely control the dual graphics card separately in a web page, such as on/off/restart.
The controller can be moved and placed at will
Because it uses a reverse proxy function, for example, my graphics card uses ports 5090 and 4090 to boot, and it can be controlled centrally by reverse proxy to port 8000, and the original web page can also be opened separately through ports 5090 and 4090, which will not interfere with the existing code.
These are screenshots of the features:

<img width="1200" height="2350" alt="image" src="https://github.com/user-attachments/assets/49aa5058-45cc-4566-a7f9-09b379182ddf" />

放在ComfyUI_windows_portable根目录中，在文件夹空白处右键打开powershell，运行python comfy_web.py
打开端口8000即可访问，或者本机访问: localhost:8000
因为用了fastAPI等，所以初次运行可能需要安装，报错可以截图问GPT

------------翻译/translate-----

Place it in the root directory of ComfyUI_windows_portable. Right-click a blank area in the folder to open PowerShell and run `python comfy_web.py`.
Open port 8000 to access it, or access it locally: localhost:8000.
Because it uses fastAPI and other features, you may need to install it the first time. If you encounter any errors, take a screenshot and ask GPT.

<img width="1638" height="959" alt="image" src="https://github.com/user-attachments/assets/5af08a35-f94a-45a4-85c9-5e0db8ad1ed1" />
<img width="1120" height="576" alt="image" src="https://github.com/user-attachments/assets/e1222e89-c2c9-4959-ae57-ed8dafc3a914" />
