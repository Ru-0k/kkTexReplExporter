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


def upd_idx(old_len, new_len, idxlist, pos, firstconf):
    # 根据替换造成的长度差值更新其后的索引
    diff = new_len - old_len
    if diff != 0:
        for j in range(3):
            idxlist[pos][j] += firstconf[j] * diff # 对当前所处图片的索引的设置，例如firstconf=[0,1,1]即代表从idxlist[pos][1]开始修改
        if pos + 1 < len(idxlist): # 若当前所处图片是最后一个，则无需更新
            for i in range(pos + 1, len(idxlist)):
                for j in range(3):
                    idxlist[i][j] += diff
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

    count = 0
    idx = [[0,0,0]]
    start_idx = 0

    # Get the directory and filename
    directory, filename = os.path.split(input_file_path)
    filename_without_extension, file_extension = os.path.splitext(filename)

    # 新建文件夹用于内嵌图片导出
    extracted_dirname = f"{filename_without_extension}_extracted"
    extracted_path = os.path.join(directory, extracted_dirname)
    os.makedirs(extracted_path, exist_ok=True)

    while True:
        idx.append([0, data.find(start_marker, start_idx), data.find(end_marker, start_idx) + len(end_marker)])

        if idx[count+1][1] != -1 and idx[count+1][2] != -1:
            count += 1
            new_file_data = data[idx[count][1]:idx[count][2]]

            # Create a new filename and path
            new_filename = f"{filename_without_extension}_{count:03d}{file_extension}"
            new_file_path = os.path.join(extracted_path, new_filename)

            # Write the new file
            with open(new_file_path, 'wb') as new_file:
                new_file.write(new_file_data)

            start_idx = idx[count][2]
        else:
            idx.pop()
            break

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
        idx_new = [idx[i][:] for i in range(len(idx))]  # 使用切片创建新的列表，避免互相影响
        bank_count = 0

        while count > 0:
            
            # 构建所要替换的内嵌图片所处的路径
            to_overwrite_filename = f"{filename_without_extension}_{count:03d}{file_extension}"
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
            overwrt_data = overwrt_data[:idx[count][1]] + to_overwrite_file_data + overwrt_data[idx[count][2]:]
            to_overwrite_file_len = len(to_overwrite_file_data)

            # 根据替换造成的长度差值更新索引
            upd_idx((idx[count][2] - idx[count][1]), to_overwrite_file_len, idx_new, count, [0, 0, 1])

            if count > 2: 
                # 旧长度标志
                _, old_len_offset = getlen(idx[count][2] - idx[count][1])
                idx[count][0] = idx[count][1] - old_len_offset - 1
                idx_new[count][0] = idx[count][0]

                # 新长度标志
                data_len_to_update, data_len_offset = getlen(to_overwrite_file_len)
                overwrt_data = overwrt_data[:(idx_new[count][1] - old_len_offset - 1)] + bytes.fromhex(data_len_to_update) + overwrt_data[idx_new[count][1]:]
                
                # 更新长度标志后的索引
                upd_idx(old_len_offset, data_len_offset, idx_new, count, [0, 1, 1])


            # 若该内嵌图片前有贴图库或纹理库的起始标志，则需对该库的长度标志作对应修改
            txtrdic_idx = overwrt_data.rfind(txtrdic_marker, idx_new[count-1][2], idx_new[count][1])
            overlay_idx = overwrt_data.rfind(overlay_marker, idx_new[count-1][2], idx_new[count][1])
            if (txtrdic_idx != -1) or (overlay_idx != -1): 
                if (txtrdic_idx != -1) and (overlay_idx != -1): 
                    raise ValueError
                # ↑如此可保证进行到这里是一个值一个-1

                # 得到库起始索引
                bank_idx = txtrdic_idx + overlay_idx + 1

                # 得到库长度标志索引
                if txtrdic_idx != -1: 
                    banklen_idx = bank_idx + len(txtrdic_marker)
                elif overlay_idx != -1: 
                    banklen_idx = bank_idx + len(overlay_marker)

                # 得到库末尾索引
                if bank_count == 0: # 若是第一次进行库长度标志修改，则将全文件内最后一个内嵌图片的末尾作为库末尾
                    bankend_idx = idx_new[len(idx_new) -1][2]
                else: # 若不是，则将上一个库的起始标志之前的内嵌图片的末尾作为库末尾
                    bankend_idx = idx_new[count_endi][2]

                # 得到库内容起始索引，即长度标志对应长度的字节序列的起始
                old_len_offset = 2 ** (overwrt_data[banklen_idx] - 0xc4) # 旧长度标志
                bankstart_idx = banklen_idx + 1 + old_len_offset

                # 新长度标志
                data_len_to_update, data_len_offset = getlen(bankend_idx - bankstart_idx + (overlay_idx != -1)) # Overlay数据末尾比其包含的最后一个文件尾多了一字节0xc2，因此补1
                overwrt_data = overwrt_data[:banklen_idx] + bytes.fromhex(data_len_to_update) + overwrt_data[bankstart_idx:]

                # 更新长度标志后的索引
                upd_idx(old_len_offset, data_len_offset, idx_new, count, [1, 1, 1])

                # 更新标志
                count_endi = count - 1
                bank_count += 1


            if count == 2: # 证件照

                # 获取证件照长度并转换端序
                data_len_to_update = bytes.fromhex(f"{to_overwrite_file_len:08x}")[::-1]

                # 覆盖证件照长度标志
                overwrt_data = overwrt_data[:idx_new[count][1] - 4] + data_len_to_update + overwrt_data[idx_new[count][1]:]

            count -= 1

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
