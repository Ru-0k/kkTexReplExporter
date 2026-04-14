import os
import shutil

# --- 魔数常量 ---
PNG_START        = bytes.fromhex('89504e47')
PNG_END          = bytes.fromhex('ae426082')
JPEG_START       = bytes.fromhex('FFD8FF')
WEBP_RIFF        = bytes.fromhex('52494646')
WEBP_SIG         = bytes.fromhex('57454250')
TXTRDIC_MARKER   = b'TextureDictionary'  # 纹理库标志
OVERLAY_MARKER   = b'Overlays'           # 贴图库标志
TEXTUREID_PREFIX = b'_TextureID_'        # 散图片标志前缀
TEXTUREID_TOTAL_LEN = len(TEXTUREID_PREFIX) + 4  # _TextureID_ + 4位数字 = 15字节


def getlen(length_of_bytes, type=None):
    length_of_bytes = int(length_of_bytes)

    while 0 <= length_of_bytes <= 0xffffffff:

        while type != None:  # 若定义了长度，则强行转换
            if (type == 1):
                return f"c4{length_of_bytes:02x}", 1
            elif (type == 2):
                return f"c5{length_of_bytes:04x}", 2
            elif (type == 4) or (type == 3):
                return f"c6{length_of_bytes:08x}", 4
            else:
                raise ValueError

        # 若未定义长度，则判断长度，将数值转化为4字节十六进制数，并找出第一个非零字节
        type = 4 - next((i for i, byte in enumerate(bytes.fromhex(f"{length_of_bytes:08x}")) if byte != 0), -1)

    raise ValueError


def read_getlen(data, pos):
    """读取 getlen() 格式的长度标志（c4/c5/c6 + 大端序长度值）。
    返回 (value, len_bytes)，len_bytes 为长度字段的字节数（不含类型字节）。"""
    type_byte = data[pos]
    if type_byte not in (0xc4, 0xc5, 0xc6):
        raise ValueError(f"read_getlen: 非法类型字节 0x{type_byte:02x}（位置 {pos}）")
    len_bytes = 2 ** (type_byte - 0xc4)  # c4→1, c5→2, c6→4
    value = int.from_bytes(data[pos + 1 : pos + 1 + len_bytes], 'big')
    return value, len_bytes


def get_image_extension(data):
    """从图片数据的魔数检测格式，返回扩展名（.png / .jpg / .webp）。"""
    if len(data) >= 4 and data[:4] == PNG_START:
        return '.png'
    if len(data) >= 3 and data[:3] == JPEG_START:
        return '.jpg'
    if len(data) >= 12 and data[:4] == WEBP_RIFF and data[8:12] == WEBP_SIG:
        return '.webp'
    return '.png'  # 兜底


def find_valid_library_marker(data, marker, from_pos):
    """查找库标志（TextureDictionary / Overlays），要求其紧跟的字节是 c4/c5/c6，
    否则视为误匹配继续搜索。返回库标志起始位置，未找到则返回 -1。"""
    pos = from_pos
    while True:
        found = data.find(marker, pos)
        if found == -1:
            return -1
        after = found + len(marker)
        if after < len(data) and data[after] in (0xc4, 0xc5, 0xc6):
            return found
        pos = found + 1  # 该处是误匹配，从下一个字节继续搜索


def find_texture_id_marker(data, from_pos):
    """查找 _TextureID_\\d{4} 模式（后需紧跟 c4/c5/c6 类型字节）。
    返回该模式起始位置，未找到则返回 -1。"""
    pos = from_pos
    while True:
        found = data.find(TEXTUREID_PREFIX, pos)
        if found == -1:
            return -1
        end = found + TEXTUREID_TOTAL_LEN
        if end >= len(data):
            return -1
        digits = data[found + len(TEXTUREID_PREFIX) : end]
        if all(0x30 <= b <= 0x39 for b in digits) and data[end] in (0xc4, 0xc5, 0xc6):
            return found
        pos = found + 1


def find_all_image_starts(data, from_pos, to_pos):
    """在 [from_pos, to_pos) 范围内查找所有图片起始位置（PNG/JPEG/WEBP 魔数）。"""
    starts = []
    pos = from_pos
    while pos < to_pos:
        png_pos  = data.find(PNG_START,  pos, to_pos)
        jpeg_pos = data.find(JPEG_START, pos, to_pos)
        # WEBP 需验证 RIFF + 偏移8处的 WEBP 标志
        webp_pos = -1
        webp_search = pos
        while webp_search < to_pos:
            riff = data.find(WEBP_RIFF, webp_search, to_pos)
            if riff == -1 or riff + 12 > to_pos:
                break
            if data[riff + 8 : riff + 12] == WEBP_SIG:
                webp_pos = riff
                break
            webp_search = riff + 1

        candidates = [p for p in (png_pos, jpeg_pos, webp_pos) if p != -1]
        if not candidates:
            break
        next_start = min(candidates)
        starts.append(next_start)
        pos = next_start + 1
    return starts


def find_getlen_before(data, img_start, bank_content_start, bank_end):
    """在图片起始位置之前寻找紧贴的 getlen() 类型字节（c4/c5/c6）。
    bank_content_start：lenPos 不得低于此值；bank_end：imgEnd 不得超过此值。
    返回 (len_pos, value)，未找到则返回 None。"""
    # 尝试 c4（1字节长度），len_pos = img_start - 2
    if img_start - 2 >= bank_content_start and data[img_start - 2] == 0xc4:
        value = data[img_start - 1]
        if img_start + value <= bank_end:
            return img_start - 2, value
    # 尝试 c5（2字节长度），len_pos = img_start - 3
    if img_start - 3 >= bank_content_start and data[img_start - 3] == 0xc5:
        value = int.from_bytes(data[img_start - 2 : img_start], 'big')
        if img_start + value <= bank_end:
            return img_start - 3, value
    # 尝试 c6（4字节长度），len_pos = img_start - 5
    if img_start - 5 >= bank_content_start and data[img_start - 5] == 0xc6:
        value = int.from_bytes(data[img_start - 4 : img_start], 'big')
        if img_start + value <= bank_end:
            return img_start - 5, value
    return None


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
    #     "lenPos":     int,   # getlen() 类型字节位置；id_photo 为 LE 大小标志起始；special 为 0
    #     "start":      int,   # 图片数据起始位置
    #     "end":        int,   # 图片数据末尾位置（不含）
    #     "cat":        str,   # "special" | "id_photo" | "TextureDictionary" | "Overlays" | "standalone"
    #     "bank_first": bool,  # 是否是某个贴图库的第一个贴图（紧随库大小标志之后）
    #     "ext":        str,   # 图片扩展名：".png" | ".jpg" | ".webp"
    #   }
    textures = []

    # ── 1. 卡面（第一个 PNG，无大小标志，必须是 PNG）──────────────────────
    cf_start = data.find(PNG_START)
    cf_end_raw = data.find(PNG_END)
    if cf_start == -1 or cf_end_raw == -1:
        print("未找到卡面图片")
        return
    cf_end = cf_end_raw + len(PNG_END)
    textures.append({"lenPos": 0, "start": cf_start, "end": cf_end,
                     "cat": "special", "bank_first": False, "ext": ".png"})

    # ── 2. 证件照（第二个 PNG，4字节小端序大小标志，必须是 PNG）──────────
    id_start = data.find(PNG_START, cf_end)
    id_end_raw = data.find(PNG_END, cf_end)
    if id_start == -1 or id_end_raw == -1:
        print(f"扫描完成：共 {len(textures)} 个内嵌图片（未找到证件照）")
    else:
        id_end = id_end_raw + len(PNG_END)
        textures.append({"lenPos": id_start - 4, "start": id_start, "end": id_end,
                         "cat": "id_photo", "bank_first": False, "ext": ".png"})

        # ── 3+. 纹理库、贴图库、散图片（getlen() 大小标志，png/jpg/webp）──
        scan_pos = id_end

        while scan_pos < len(data):
            tx_pos = find_valid_library_marker(data, TXTRDIC_MARKER, scan_pos)
            ov_pos = find_valid_library_marker(data, OVERLAY_MARKER, scan_pos)
            ti_pos = find_texture_id_marker(data, scan_pos)

            candidates = []
            if tx_pos != -1: candidates.append((tx_pos, "TextureDictionary"))
            if ov_pos != -1: candidates.append((ov_pos, "Overlays"))
            if ti_pos != -1: candidates.append((ti_pos, "standalone"))
            if not candidates:
                break

            nearest_pos, nearest_type = min(candidates, key=lambda x: x[0])

            if nearest_type == "standalone":
                # 散图片：_TextureID_XXXX + getlen() + 图片数据
                len_pos = nearest_pos + TEXTUREID_TOTAL_LEN
                img_size, len_bytes = read_getlen(data, len_pos)
                img_start = len_pos + 1 + len_bytes
                img_end = img_start + img_size
                img_ext = get_image_extension(data[img_start:img_end])
                textures.append({"lenPos": len_pos, "start": img_start, "end": img_end,
                                 "cat": "standalone", "bank_first": False, "ext": img_ext})
                scan_pos = img_end

            else:
                # 库（TextureDictionary 或 Overlays）
                marker = TXTRDIC_MARKER if nearest_type == "TextureDictionary" else OVERLAY_MARKER
                banklen_pos = nearest_pos + len(marker)
                bank_size, bank_len_bytes = read_getlen(data, banklen_pos)
                bank_content_start = banklen_pos + 1 + bank_len_bytes
                bank_end = bank_content_start + bank_size

                # Overlays 库内容末尾有一字节 0xc2，不属于任何图片
                img_scan_end = bank_end - 1 if nearest_type == "Overlays" else bank_end

                # 库内图片之间（以及库大小标志之后、第一张图之前）可能存在任意数据，
                # 需通过魔数定位每张图片的起始位置
                img_starts = find_all_image_starts(data, bank_content_start, img_scan_end)
                is_first = True
                last_img_end = bank_content_start

                for img_start in img_starts:
                    if img_start < last_img_end:
                        continue
                    result = find_getlen_before(data, img_start, bank_content_start, img_scan_end)
                    if result is None:
                        continue  # 无法找到紧贴的 getlen()，跳过此误匹配
                    len_pos, img_size = result
                    img_end = img_start + img_size
                    img_ext = get_image_extension(data[img_start:img_end])
                    textures.append({"lenPos": len_pos, "start": img_start, "end": img_end,
                                     "cat": nearest_type, "bank_first": is_first, "ext": img_ext})
                    is_first = False
                    last_img_end = img_end

                scan_pos = bank_end

    count = len(textures)

    # 导出所有内嵌图片
    for i, tex in enumerate(textures):
        tex_num = i + 1
        new_filename = f"{filename_without_extension}_{tex_num:03d}{tex['ext']}"
        new_file_path = os.path.join(extracted_path, new_filename)
        with open(new_file_path, 'wb') as new_file:
            new_file.write(data[tex["start"]:tex["end"]])

    print(f"{count}个内嵌图片已导出到新建文件夹：{extracted_path}")

    overwrite_flag = str(input("若要替换内嵌图片, 请输入1: "))
    if (overwrite_flag == '1'):
        new_folder_flag = str(input("若要将内嵌图片复制到新建文件夹以便替换, 请输入2, 否则直接回车: "))
        if (new_folder_flag == '2'):
            to_overwrite_dirname = f"{filename_without_extension}_to_overwr"
            to_overwrite_dir_path = os.path.join(directory, to_overwrite_dirname)
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
            to_overwrite_filename = f"{filename_without_extension}_{i+1:03d}{tex['ext']}"
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
                # 更新该贴图的 getlen() 大小标志
                _, old_len_offset = getlen(tex["end"] - tex["start"])
                textures[i]["lenPos"] = tex["start"] - old_len_offset - 1
                textures_new[i]["lenPos"] = textures[i]["lenPos"]

                data_len_to_update, data_len_offset = getlen(to_overwrite_file_len)
                overwrt_data = overwrt_data[:(textures_new[i]["start"] - old_len_offset - 1)] + bytes.fromhex(data_len_to_update) + overwrt_data[textures_new[i]["start"]:]

                upd_idx(old_len_offset, data_len_offset, textures_new, i, [0, 1, 1])

            # 若该贴图是某个库的首个贴图，则需对该库的长度标志作对应修改
            if tex["bank_first"]:
                bank_marker = TXTRDIC_MARKER if tex["cat"] == "TextureDictionary" else OVERLAY_MARKER

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
                data_len_to_update, data_len_offset = getlen(bankend_idx - bankstart_idx + (tex["cat"] == "Overlays"))  # Overlay数据末尾比其包含的最后一个文件尾多了一字节0xc2，因此补1
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
