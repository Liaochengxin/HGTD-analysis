# -*- coding: utf-8 -*-
import subprocess
import os
import sys

# 确保模板文件存在
TEMPLATE_FILE = 'Card52_v3.C'
if not os.path.exists(TEMPLATE_FILE):
    print(f"错误：找不到模板文件 {TEMPLATE_FILE}，请确保它存在于当前目录。")
    sys.exit(1)

# 读取模板
with open(TEMPLATE_FILE, 'r') as f:
    CTcode = f.read()

# ================ 在此处修改你要分析的晶圆列表 ================
# 格式：(batch, wafer, temperature)
input_list = [
    (15, 7, 20.9),
        # 你可以添加或删除，按需修改
]
# ============================================================

# 创建输出目录（存放生成的 .C 和 .sh 文件）
output_dir = "./generated"
os.makedirs(output_dir, exist_ok=True)

# 获取当前所在的 WSL 工作目录（也就是桌面的绝对路径）
base_dir = os.getcwd()
# 指定数据文件夹路径（同时也是图片文件的输出路径）
target_data_dir = os.path.join(base_dir, "15007")

print(f"📂 目标数据/输出目录: {target_data_dir}")

# 询问温度（所有芯片使用同一个温度）
print("\n🌡️  请输入测试温度（所有芯片将使用相同温度）")
while True:
    try:
        Tp_input = float(input("   温度 (°C): "))
        break
    except ValueError:
        print("   ❌ 请输入有效的数字！")
print(f"   ✅ 温度设置为: {Tp_input}°C")
print("=" * 60)

for batchnum, wafernum, Tp in input_list:
    # 使用手动输入的温度覆盖列表中的温度
    Tp = Tp_input
    
    # 生成新的 .C 文件名
    newC = os.path.join(output_dir, f"Code_{batchnum}_{wafernum}.C")
    
    # 替换占位符
    CMcode = CTcode.replace('REPLACE_BATCHNUM', str(batchnum))
    CMcode = CMcode.replace('REPLACE_WAFERNUM', str(wafernum))
    CMcode = CMcode.replace('REPLACE_TEMPERATURE', str(Tp))
    CMcode = CMcode.replace('Card52_v3', f'Code_{batchnum}_{wafernum}')
    
    # 写入 .C 文件
    with open(newC, 'w') as f:
        f.write(CMcode)
    print(f"✅ 已生成: {newC}")
    
    # 生成 Shell 脚本
    shell_script = os.path.join(output_dir, f"job_{batchnum}_{wafernum}.sh")
    # 获取 newC 的绝对路径，避免 cd 切换目录后找不到文件
    newC_abs = os.path.abspath(newC)
    
    with open(shell_script, 'w') as f:
        f.write("#!/bin/bash\n")
        # 1. 切换工作目录到数据文件夹，保证所有图片保存到此处
        f.write(f"cd \"{target_data_dir}\"\n")
        # 2. 使用 echo 自动把温度传给 ROOT 程序，避免手动输入导致的卡死
        f.write(f"echo \"{Tp}\" | root -l -q '{newC_abs}'\n")
        f.write("exit $?\n")
    
    # 赋予可执行权限
    os.chmod(shell_script, 0o755)
    print(f"✅ 已生成: {shell_script}")
    
    # 执行该 Shell 脚本
    print(f"🚀 正在运行: {shell_script} ...")
    ret = subprocess.call(['bash', shell_script])
    if ret != 0:
        print(f"⚠️ 警告：{shell_script} 执行失败，返回码 {ret}")
    else:
        print(f"🎉 完成: {shell_script}")

print("✨ 所有任务处理完毕。")