import os

# 项目根目录
project_root = r"D:\桌面\AAA"  # 可以改成你想创建的路径

# 项目结构
structure = {
    "src": ["main.py", "serial_manager.py", "parser.py", "utils.py", "virtual_sender.py"],
    "requirements.txt": None,
    "README.md": None,
}

# 文件默认内容模板
file_contents = {
    "requirements.txt": "pyqt5\npyqtgraph\npyserial\n",
    "README.md": "# Serial ADC Viewer\n\n上位机工程模板，使用 PyQt5 + pyqtgraph 实现实时串口 ADC 数据显示。\n",
    "main.py": "# main.py\n# 这里放 GUI 主程序代码\n",
    "serial_manager.py": "# serial_manager.py\n# 这里放串口管理代码\n",
    "parser.py": "# parser.py\n# 这里放数据解析代码\n",
    "utils.py": "# utils.py\n# 这里放 CRC 等工具函数\n",
    "virtual_sender.py": "# virtual_sender.py\n# 这里放虚拟发送器示例代码\n",
}

def create_structure(root, struct):
    os.makedirs(root, exist_ok=True)
    for name, subfiles in struct.items():
        path = os.path.join(root, name)
        if isinstance(subfiles, list):
            # 创建子目录
            os.makedirs(path, exist_ok=True)
            for f in subfiles:
                f_path = os.path.join(path, f)
                with open(f_path, "w", encoding="utf-8") as fw:
                    fw.write(file_contents.get(f, ""))
        else:
            # 创建文件
            with open(path, "w", encoding="utf-8") as fw:
                fw.write(file_contents.get(name, ""))

if __name__ == "__main__":
    create_structure(project_root, structure)
    print(f"项目目录已生成在 {project_root}")
