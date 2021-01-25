#!/usr/bin/env python3
import os
import sys
import sane
import time
from configparser import ConfigParser
from pdb import set_trace

ocr = False

def select(l):
    for i, el in enumerate(l):
        print('[%s] %s' % (i, el))
    i_ = int(sys.stdin.readline())

    print('selected %s.' % l[i_])
    return l[i_]

def threshold_inc():
    print('threshold increment:')
    ret = sys.stdin.readline()
    return int(ret) 

def calc_page_params(perpage, righttoleft, startat, last, inc, turnbyturn):
    current = last+inc
    if perpage == 2:
        # [page000] -3, -4
        # [page001] -1, -2
        # [page002]  1,  0
        # [page003]  3,  2
        left = perpage*(last+inc)+righttoleft+startat
        right = perpage*(last+inc)+(1-righttoleft)+startat
        msg = '[page%03d] left:p.%s, right:p.%s' % (current, left, right)
    else:
        msg = '[page%03d] p.%s' % (current, current+startat)

    if turnbyturn:
        rot_turn = 180*(current%2-(righttoleft)) # 右から左だと、反転から始まる
    else:
        rot_turn = 180

    if rot_turn == 0: # ロゴと同じ向きが rot_turn==180
        msg += '\nupsidedown relative to EPSON logo'
    return msg, rot_turn

def main():
    if os.path.exists('setting.ini'):
        config = ConfigParser()
        config.read('setting.ini')

        scanner = config.getint('DEFAULT', 'scanner')
        scan_area = config.get('DEFAULT', 'scan_area')
        rot = config.getint('DEFAULT', 'rot') * 90
        turnbyturn = config.getint('DEFAULT', 'turnbyturn')
        righttoleft = config.getint('DEFAULT', 'righttoleft')
        perpage = config.getint('DEFAULT', 'perpage')
        threshold = config.getint('DEFAULT', 'threshold')
        startat = config.getint('DEFAULT', 'startat')
        firsttime = False
    else:
        scanner = None
        scan_area = 'A4'
        rot = 0
        perpage = 1
        threshold = 128
        firsttime = True

    sane.init()

    devices = sane.get_devices()
    if scanner is not None:
        print('using %s...' % str(devices[scanner]))
        device = devices[scanner]
    else:
        device = select(devices)
    devname = device[0]
    dev = sane.open(devname)
    dev.scan_area = scan_area
    # set_trace()

    ret = 0
    n = -1

    while True:
        msg, rot_turn = calc_page_params(perpage, righttoleft, startat, n, 1, turnbyturn)
        print(msg)
        inc = 1
        print('press return if')
        print('%s(old n) + %s(inc) = %s(page%03d)' % (n, inc, n+inc, n+inc))
        print('is ok')
        print('or other [inc] parameter')
        ret = sys.stdin.readline()
        if ret == '\n':
            pass
        elif ret.strip().replace('-', '').isdigit():
            while True:
                inc = int(ret)
                msg, rot_turn = calc_page_params(perpage, righttoleft, startat, n, inc, turnbyturn)
                print(msg)
                print('press return if ok.')
                ret = sys.stdin.readline()
                if ret == '\n':
                    break
        else:
            dev.close()
            break

        n = n+inc
        prefix = 'page%03d' % n
        jpeg = prefix + '.jpeg'
        pbm = prefix + '.pbm'


        print('scanning %s...' % msg)
        arr = dev.scan()
        print('scanned %s.' % msg)

        if firsttime:
            arr.show()
            print('rotate? [-1:clockwise, 1:counterclockwise]')
            rot = int(sys.stdin.readline()) * 90
        else:
            arr = arr.rotate(rot, expand=True)
        
        if perpage == 1:
            arr = arr.rotate(rot_turn)

        # arr.show()
        w, h = arr.size

        if firsttime:
            print('perpage?')
            if int(sys.stdin.readline()) == 2:
                perpage = 2
            else:
                perpage = 1
            
        gray = arr.convert('L')

        inc = 1
        bw = gray.point(lambda x: 0 if x < threshold else 255, '1')
        if firsttime:
            while True:
                inc = threshold_inc()
                if inc == 0:
                    break
                threshold += inc
                print('threshold: %s' % threshold)
                bw = gray.point(lambda x: 0 if x < threshold else 255, '1')
                bw.show()

        pbm_files = []
        if perpage > 1:
            arr0 = arr.crop((0, 0, w/2, h))
            arr1 = arr.crop((w/2, 0, w, h))
            bw0 = bw.crop((0, 0, w/2, h))
            bw1 = bw.crop((w/2, 0, w, h))
            jpeg0 = 'split%03d.jpeg' % (n*2+righttoleft)
            jpeg1 = 'split%03d.jpeg' % (n*2+(1-righttoleft))
            pbm0 = 'split%03d.pbm' % (n*2+righttoleft)
            pbm1 = 'split%03d.pbm' % (n*2+(1-righttoleft))
            arr0.save(jpeg0)
            arr1.save(jpeg1)
            bw0.save(pbm0)
            bw1.save(pbm1)
            print('saved %s' % ', '.join([jpeg0, jpeg1, pbm0, pbm1]))
            pbm_files.append(pbm0)
            pbm_files.append(pbm1)
            merge_cmd = 'djvm -c merged.djvu split*_color.djvu'
            
        else:
            arr.save(jpeg)
            bw.save(pbm)
            print('saved %s' % ', '.join([jpeg, pbm]))
            pbm_files.append(pbm)
            merge_cmd = 'djvm -c merged.djvu page*_color.djvu'            

        for pbm in pbm_files:
            commands = []
            djvu = pbm.replace('pbm', 'djvu')
            commands.append('cjb2 -clean %s %s' % (pbm, djvu))
            commands.append('c44 -dpi %s %s %s' % (dev.resolution, pbm.replace('.pbm', '.jpeg'), pbm.replace('.pbm', '_color.djvu')))
            if ocr:
                commands.append('ocrodjvu --in-place -l jpn %s' % (djvu))
                commands.append('djvused %s -e "select 1; print-txt" > %s' % (djvu, djvu.replace('.djvu', '.txt')))
                commands.append('djvused %s -e "select 1; set-txt %s; save"' % (djvu.replace('.djvu', '_color.djvu'), djvu.replace('.djvu', '.txt')))

            commands.append(merge_cmd)
            for cmd in commands:
                print(cmd)
                os.system(cmd)
        
        firsttime=False
        # os.system('spd-say "ok"')
        if perpage > 1:
            os.system('spd-say "turn page"')
            time.sleep(1)
            if righttoleft:
                os.system('spd-say "right"')
            else:
                os.system('spd-say "left"')
        else:
            os.system('spd-say "go to"')
            time.sleep(1)
            if righttoleft:
                os.system('spd-say "left"')
            else:
                os.system('spd-say "right"')
        time.sleep(1)
        os.system('spd-say "page %s"' % ((n+1)*perpage+startat))

    sane.exit()
    
if __name__ == '__main__':
    main()
