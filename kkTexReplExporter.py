import os
import shutil

def getlen(length_of_bytes, type = None):
    length_of_bytes = int(length_of_bytes)

    while 0 <= length_of_bytes <= 0xffffffff:

        while type != None: # 若定义了长度，则强行转换
            if (type == 1): # (0 <= length_of_bytes <= 0xff) or
                return f"c4{length_of_bytes:02x}", 1
            elif (type == 2): # (0x100 <= length_of_bytes <= 0xffff) or
                return f"c5{length_of_bytes:04x}", 2
            elif (type == 4) or (type == 3): # (0x10000 <= length_of_bytes <= 0xffffffff) or
                return f"c6{length_of_bytes:08x}", 4
            else:
                raise ValueError

        # 若未定义长度，则判断长度，将数值转化为4字节十六进制数，并找出第一个非零字节
        type = 4 - next((i for i, byte in enumerate(bytes.fromhex(f"{length_of_bytes:08x}")) if byte != 0), -1)

    raise ValueError


def upd_idx(old_len, new_len, textures, pos, firstconf):
    # 根据替换造成的长度差值更新其后的索引
    # firstconf 对应 ["lenPos", "start", "end"] 三个字段的更新开关
    keys = ["lenPos", "start", "end"]
    diff = new_len - old_len
    if diff != 0:
        for j, key in enumerate(keys):
            textures[pos][key] += firstconf[j] * diff  # 对当前所处贴图的索引作设置
        for i in range(pos + 1, len(textures)):         # 更新其后所有贴图的索引
            for key in keys:
                textures[i][key] += diff
    # 由于列表是引用的，因而无需回传


def copy_hex_content(input_file_path):
    try:
        with open(input_file_path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        print(f"文件 '{input_file_path}' 未找到")
        return

    start_marker = bytes.fromhex('89504e47')
    end_marker = bytes.fromhex('ae426082')
    txtrdic_marker = b'TextureDictionary' # materialeditor后的"TextureDictionary", ME的纹理库
    overlay_marker = b'Overlays' # "Overlays", 贴图库

    # Get the directory and filename
    directory, filename = os.path.split(input_file_path)
    filename_without_extension, file_extension = os.path.splitext(filename)

    # 新建文件夹用于内嵌图片导出
    extracted_dirname = f"{filename_without_extension}_extracted"
    extracted_path = os.path.join(directory, extracted_dirname)
    os.makedirs(extracted_path, exist_ok=True)

    # 扫描所有内嵌贴图并按类别归类
    # textures 中每个元素为：
    #   {
    #     "lenPos":    int,   # msgpack 长度标志的位置（"special"/"id_photo"类为0，暂不使用）
    #     "start":     int,   # PNG 数据起始位置
    #     "end":       int,   # PNG 数据末尾位置（不含）
    #     "cat":       str,   # 类别："special" | "id_photo" | "TextureDictionary" | "Overlays"
    #     "bank_first": bool, # 是否是某个贴图库的第一个贴图（即紧随库标志之后）
    #   }
    textures = []
    start_idx = 0

    while True:
        s = data.find(start_marker, start_idx)
        e = data.rfind(end_marker, start_idx)  # 用rfind防止中间出现误匹配
        if s == -1 or e == -1 or e <= s:
            break
        e += len(end_marker)

        tex_num = len(textures) + 1  # 当前是第几个贴图（1-based，便于理解）

        if tex_num == 1:
            cat = "special"
            bank_first = False
        elif tex_num == 2:
            cat = "id_photo"   # 证件照，长度字节序与其他不同
            bank_first = False
        else:
            # 在上一个贴图末尾到当前贴图起始之间，查找库标志
            prev_end = textures[-1]["end"]
            if data.rfind(txtrdic_marker, prev_end, s) != -1:
                cat = "TextureDictionary"
                bank_first = True
            elif data.rfind(overlay_marker, prev_end, s) != -1:
                cat = "Overlays"
                bank_first = True
            else:
                # 继承上一个贴图的类别（同一个库内的连续贴图）
                cat = textures[-1]["cat"]
                bank_first = False

        textures.append({"lenPos": 0, "start": s, "end": e, "cat": cat, "bank_first": bank_first})

        # 导出该贴图到文件
        new_filename = f"{filename_without_extension}_{tex_num:03d}{file_extension}"
        new_file_path = os.path.join(extracted_path, new_filename)
        with open(new_file_path, 'wb') as new_file:
            new_file.write(data[s:e])

        start_idx = e

    count = len(textures)
    print(f"{count}个内嵌图片已导出到新建文件夹：{extracted_path}")

    overwrite_flag = str(input("若要替换内嵌图片, 请输入1: "))
    if (overwrite_flag == '1'):
        new_folder_flag = str(input("若要将内嵌图片复制到新建文件夹以便替换, 请输入2, 否则直接回车: "))
        if (new_folder_flag == '2'):
            to_overwrite_dirname = f"{filename_without_extension}_to_overwr"
            to_overwrite_dir_path = os.path.join(directory, to_overwrite_dirname)
            # os.makedirs(to_overwrite_dir_path, exist_ok=True)
            shutil.copytree(extracted_path, to_overwrite_dir_path, dirs_exist_ok=True)
            print(f"已在源文件所在文件夹新建了文件夹 {filename_without_extension}_to_overwr, 并已向其中复制了已导出的所有内嵌图片")
        else:
            to_overwrite_dir_path = str(input("请输入所要替换的内嵌图片所处的文件夹路径, 保持新内嵌图片与所要替换的已导出的原内嵌图片文件名相同: "))

        _ = str(input("现在可以修改编辑内嵌图片，完成后按回车即对内嵌图片进行替换: "))

        # 重置变量
        overwrt_data = data
        textures_new = [dict(t) for t in textures]  # 浅拷贝每个字典（值均为基本类型，足够）
        bank_count = 0
        count_endi = 0

        for i in range(count - 1, -1, -1):  # 从最后一个贴图倒序处理
            tex = textures[i]

            # 构建所要替换的内嵌图片的路径（文件名用1-based序号）
            to_overwrite_filename = f"{filename_without_extension}_{i+1:03d}{file_extension}"
            to_overwrite_file_path = os.path.join(to_overwrite_dir_path, to_overwrite_filename)

            # 若不存在，则用已导出的原文件
            try:
                with open(to_overwrite_file_path, 'rb') as f:
                    to_overwrite_file_data = f.read()
            except FileNotFoundError:
                to_overwrite_file_path = os.path.join(extracted_path, to_overwrite_filename)
                with open(to_overwrite_file_path, 'rb') as f:
                    to_overwrite_file_data = f.read()

            # 读取所要替换的内嵌图片并覆盖
            overwrt_data = overwrt_data[:textures_new[i]["start"]] + to_overwrite_file_data + overwrt_data[textures_new[i]["end"]:]
            to_overwrite_file_len = len(to_overwrite_file_data)

            # 根据替换造成的长度差值更新索引
            upd_idx((tex["end"] - tex["start"]), to_overwrite_file_len, textures_new, i, [0, 0, 1])

            if tex["cat"] not in ("special", "id_photo"):
                # 更新该贴图的 msgpack 长度标志
                _, old_len_offset = getlen(tex["end"] - tex["start"])
                textures[i]["lenPos"] = tex["start"] - old_len_offset - 1
                textures_new[i]["lenPos"] = textures[i]["lenPos"]

                data_len_to_update, data_len_offset = getlen(to_overwrite_file_len)
                overwrt_data = overwrt_data[:(textures_new[i]["start"] - old_len_offset - 1)] + bytes.fromhex(data_len_to_update) + overwrt_data[textures_new[i]["start"]:]

                upd_idx(old_len_offset, data_len_offset, textures_new, i, [0, 1, 1])


            # 若该贴图是某个库的首个贴图，则需对该库的长度标志作对应修改
            if tex["bank_first"]:
                bank_marker = txtrdic_marker if tex["cat"] == "TextureDictionary" else overlay_marker

                # 在前一个贴图末尾到当前贴图起始之间搜索库标志
                prev_end = textures_new[i - 1]["end"] if i > 0 else 0
                bank_idx = overwrt_data.rfind(bank_marker, prev_end, textures_new[i]["start"])
                banklen_idx = bank_idx + len(bank_marker)

                # 得到库末尾索引
                if bank_count == 0:
                    bankend_idx = textures_new[-1]["end"]
                else:
                    bankend_idx = textures_new[count_endi]["end"]

                # 得到库内容起始索引
                old_len_offset = 2 ** (overwrt_data[banklen_idx] - 0xc4)
                bankstart_idx = banklen_idx + 1 + old_len_offset

                # 新长度标志
                data_len_to_update, data_len_offset = getlen(bankend_idx - bankstart_idx + (tex["cat"] == "Overlays")) # Overlay数据末尾比其包含的最后一个文件尾多了一字节0xc2，因此补1
                overwrt_data = overwrt_data[:banklen_idx] + bytes.fromhex(data_len_to_update) + overwrt_data[bankstart_idx:]

                # 更新长度标志后的索引
                upd_idx(old_len_offset, data_len_offset, textures_new, i, [1, 1, 1])

                count_endi = i - 1
                bank_count += 1


            if tex["cat"] == "id_photo":
                # 证件照：获取长度并转换端序
                data_len_to_update = bytes.fromhex(f"{to_overwrite_file_len:08x}")[::-1]
                overwrt_data = overwrt_data[:textures_new[i]["start"] - 4] + data_len_to_update + overwrt_data[textures_new[i]["start"]:]

        new_filename = f"{filename_without_extension}_replaced{file_extension}"
        new_file_path = os.path.join(directory, new_filename)
        with open(new_file_path, 'wb') as new_file:
            new_file.write(overwrt_data)
        print(f"已替换内嵌图片的源文件已导出到：{new_file_path}")
        return

    if count == 0:
        print("未找到指定的标记内容")

if __name__ == "__main__":
    file_path = input("请输入源文件路径，回车即开始导出：")
    copy_hex_content(file_path)
