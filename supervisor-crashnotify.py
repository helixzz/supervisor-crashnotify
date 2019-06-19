#!/usr/bin/python
# -*- coding: utf-8 -*-
# Zijing Guo
# Forked from crashmail.py @ superlance

# A event listener meant to be subscribed to PROCESS_STATE_CHANGE
# events.  It will send message when processes that are children of
# supervisord transition unexpectedly to the EXITED state.

import os
import socket
import sys
import json
import time
import logging
import requests
from supervisor import childutils
try:
    JSONDecodeError = json.decoder.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError

# Usage
doc = """\
crashnotify.py [-p process_name] [-a] [-o string] [-t access_token]
              URL

Options:

-p -- specify a supervisor process_name.  Send mail when this process
      transitions to the EXITED state unexpectedly. If this process is
      part of a group, it can be specified using the
      'process_name:group_name' syntax.

-a -- Send mail when any child of the supervisord transitions
      unexpectedly to the EXITED state unexpectedly.  Overrides any -p
      parameters passed in the same crashnotify process invocation.

-o -- Specify a parameter used as a prefix in the mail subject header.

-t -- Specify Dingtalk robot's access token.

The -p option may be specified more than once, allowing for
specification of multiple processes.  Specifying -a overrides any
selection of -p.

A sample invocation:

crashnotify.py -p program1 -p group1:program2 -t abcdefghijkl

"""

def usage():
    print 'parameter error'
#    print doc
    sys.exit(255)

def is_not_null_and_blank_str(content):
    """
    判断字符串是否非空，避免提交无效请求。
    :param content: 字符串
    :return: 非空 - True，空 - False
    """
    if content and content.strip():
        return True
    else:
        return False

class DingtalkChatbot(object):
    """
    钉钉群自定义机器人（每个机器人每分钟最多发送20条），支持文本（text）、连接（link）、markdown三种消息类型。
    """
    def __init__(self, webhook):
        """
        机器人初始化
        :param webhook: 钉钉群自定义机器人webhook地址
        """
        super(DingtalkChatbot, self).__init__()
        self.headers = {'Content-Type': 'application/json; charset=utf-8'}
        self.webhook = webhook
        self.times = 0
        self.start_time = time.time()

    def send_text(self, msg, is_at_all=False, at_mobiles=[], at_dingtalk_ids=[]):
        """
        text类型
        :param msg: 消息内容
        :param is_at_all: @所有人时：true，否则为false（可选）
        :param at_mobiles: 被@人的手机号（可选）
        :param at_dingtalk_ids: 被@人的dingtalkId（可选）
        :return: 返回消息发送结果
        """
        data = {"msgtype": "text", "at": {}}
        if is_not_null_and_blank_str(msg):
            data["text"] = {"content": msg}
        else:
            logging.error("text类型，消息内容不能为空！")
            raise ValueError("text类型，消息内容不能为空！")

        if is_at_all:
            data["at"]["isAtAll"] = is_at_all

        if at_mobiles:
            at_mobiles = list(map(str, at_mobiles))
            data["at"]["atMobiles"] = at_mobiles

        if at_dingtalk_ids:
            at_dingtalk_ids = list(map(str, at_dingtalk_ids))
            data["at"]["atDingtalkIds"] = at_dingtalk_ids

        logging.debug('text类型：%s' % data)
        return self.post(data)

    def send_image(self, pic_url):
        """
        image类型（表情）
        :param pic_url: 图片表情链接
        :return: 返回消息发送结果
        """
        if is_not_null_and_blank_str(pic_url):
            data = {
                "msgtype": "image",
                "image": {
                    "picURL": pic_url
                }
            }
            logging.debug('image类型：%s' % data)
            return self.post(data)
        else:
            logging.error("image类型中图片链接不能为空！")
            raise ValueError("image类型中图片链接不能为空！")

    def send_link(self, title, text, message_url, pic_url=''):
        """
        link类型
        :param title: 消息标题
        :param text: 消息内容（如果太长自动省略显示）
        :param message_url: 点击消息触发的URL
        :param pic_url: 图片URL（可选）
        :return: 返回消息发送结果
        """
        if is_not_null_and_blank_str(title) and is_not_null_and_blank_str(text) and is_not_null_and_blank_str(message_url):
            data = {
                    "msgtype": "link",
                    "link": {
                        "text": text,
                        "title": title,
                        "picUrl": pic_url,
                        "messageUrl": message_url
                    }
            }
            logging.debug('link类型：%s' % data)
            return self.post(data)
        else:
            logging.error("link类型中消息标题或内容或链接不能为空！")
            raise ValueError("link类型中消息标题或内容或链接不能为空！")

    def send_markdown(self, title, text, is_at_all=False, at_mobiles=[], at_dingtalk_ids=[]):
        """
        markdown类型
        :param title: 首屏会话透出的展示内容
        :param text: markdown格式的消息内容
        :param is_at_all: 被@人的手机号（在text内容里要有@手机号，可选）
        :param at_mobiles: @所有人时：true，否则为：false（可选）
        :param at_dingtalk_ids: 被@人的dingtalkId（可选）
        :return: 返回消息发送结果
        """
        if is_not_null_and_blank_str(title) and is_not_null_and_blank_str(text):
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": text
                },
                "at": {}
            }
            if is_at_all:
                data["at"]["isAtAll"] = is_at_all

            if at_mobiles:
                at_mobiles = list(map(str, at_mobiles))
                data["at"]["atMobiles"] = at_mobiles

            if at_dingtalk_ids:
                at_dingtalk_ids = list(map(str, at_dingtalk_ids))
                data["at"]["atDingtalkIds"] = at_dingtalk_ids

            logging.debug("markdown类型：%s" % data)
            return self.post(data)
        else:
            logging.error("markdown类型中消息标题或内容不能为空！")
            raise ValueError("markdown类型中消息标题或内容不能为空！")

    def post(self, data):
        """
        发送消息（内容UTF-8编码）
        :param data: 消息数据（字典）
        :return: 返回发送结果
        """
        self.times += 1
        if self.times % 20 == 0:
            if time.time() - self.start_time < 60:
                logging.debug('钉钉官方限制每个机器人每分钟最多发送20条，当前消息发送频率已达到限制条件，休眠一分钟')
                time.sleep(60)
            self.start_time = time.time()

        post_data = json.dumps(data)
        try:
            response = requests.post(self.webhook, headers=self.headers, data=post_data)
        except requests.exceptions.HTTPError as exc:
            logging.error("消息发送失败， HTTP error: %d, reason: %s" % (exc.response.status_code, exc.response.reason))
            raise
        except requests.exceptions.ConnectionError:
            logging.error("消息发送失败，HTTP connection error!")
            raise
        except requests.exceptions.Timeout:
            logging.error("消息发送失败，Timeout error!")
            raise
        except requests.exceptions.RequestException:
            logging.error("消息发送失败, Request Exception!")
            raise
        else:
            try:
                result = response.json()
            except JSONDecodeError:
                logging.error("服务器响应异常，状态码：%s，响应内容：%s" % (response.status_code, response.text))
                return {'errcode': 500, 'errmsg': '服务器响应异常'}
            else:
                logging.debug('发送结果：%s' % result)
                if result['errcode']:
                    error_data = {"msgtype": "text", "text": {"content": "钉钉机器人消息发送失败，原因：%s" % result['errmsg']}, "at": {"isAtAll": True}}
                    logging.error("消息发送失败，自动通知：%s" % error_data)
                    requests.post(self.webhook, headers=self.headers, data=json.dumps(error_data))
                return result


class CrashNotify:
    def __init__(self, programs, any, token, optionalheader):

        self.programs = programs
        self.any = any
        self.optionalheader = optionalheader
        self.token = token
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def runforever(self, test=False):
        # 死循环, 处理完 event 不退出继续处理下一个
        while 1:
            # 使用 self.stdin, self.stdout, self.stderr 代替 sys.* 以便单元测试
            headers, payload = childutils.listener.wait(self.stdin, self.stdout)

            if test:
                self.stderr.write(str(headers) + '\n')
                self.stderr.write(payload + '\n')
                self.stderr.flush()

            if not headers['eventname'] == 'PROCESS_STATE_EXITED':
                # 如果不是 PROCESS_STATE_EXITED 类型的 event, 不处理, 直接向 stdout 写入"RESULT\nOK"
                childutils.listener.ok(self.stdout)
                continue

            # 解析 payload, 这里我们只用这个 pheaders.
            # pdata 在 PROCESS_LOG_STDERR 和 PROCESS_COMMUNICATION_STDOUT 等类型的 event 中才有
            pheaders, pdata = childutils.eventdata(payload + '\n')

            # 过滤掉 expected 的 event, 仅处理 unexpected 的
            # 当 program 的退出码为对应配置中的 exitcodes 值时, expected=1; 否则为0
            if int(pheaders['expected']):
                childutils.listener.ok(self.stdout)
                continue

            hostname = socket.gethostname()
            
            # 构造报警内容
            msg = "检测到进程异常退出。 \n - 主机： %s \n - 进程名： %s \n - PID： %s \n - 原状态： %s \n - 时间： %s" % \
                  (hostname, pheaders['processname'], pheaders['pid'], pheaders['from_state'], childutils.get_asctime())

            subject = 'Supervisor Crash Notify'
            if self.optionalheader:
                subject = '[' + self.optionalheader + ']' + subject

            self.stderr.write('Process %s unexpected exit detected, sending notification.\n' % pheaders['processname'])
            self.stderr.flush()

            self.dingrobot(self.token, subject, msg)

            # 向 stdout 写入"RESULT\nOK"，并进入下一次循环
            childutils.listener.ok(self.stdout)

    def dingrobot(self, token, subject, msg):
        webhook = 'https://oapi.dingtalk.com/robot/send?access_token=%s' % token
        bot = DingtalkChatbot(webhook)
        bot.send_markdown(title=subject, text=msg, is_at_all=True)

def main(argv=sys.argv):
    # 参数解析
    import getopt
    short_args = "hp:ao:t:"
    long_args = [
        "help",
        "program=",
        "any",
        "optional_header=",
        "access_token="
    ]
    arguments = argv[1:]
    try:
        opts, args = getopt.getopt(arguments, short_args, long_args)
    except:
        usage()

    programs = []
    any = False
    optionalheader = None

    for option, value in opts:

        if option in ('-h', '--help'):
            usage()

        if option in ('-p', '--program'):
            programs.append(value)

        if option in ('-a', '--any'):
            any = True

        if option in ('-o', '--optional_header'):
            optionalheader = value

        if option in ('-t', '--access_token'):
            token = value

    # listener 必须交由 supervisor 管理, 自己运行是不行的
    if not 'SUPERVISOR_SERVER_URL' in os.environ:
        sys.stderr.write('crashnotify must be run as a supervisor event '
                         'listener\n')
        sys.stderr.flush()
        return

    prog = CrashNotify(programs, any, token, optionalheader)
    prog.runforever(test=True)


if __name__ == '__main__':
    main()



