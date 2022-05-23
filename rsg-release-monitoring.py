import argparse
import json
import logging
import os.path
import re
import shutil
import sys
import time
from datetime import datetime
from typing import List

import requests
import urllib3
from markdown_table_generator import generate_markdown, table_from_string_list, Alignment
from requests import Response

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constants
MARKDEEP_FOOTER = '<!-- Markdeep: --><style class="fallback">body{visibility:hidden;white-space:pre;font-family:monospace}</style><script src="markdeep.min.js" charset="utf-8"></script><script src="https://morgan3d.github.io/markdeep/latest/markdeep.min.js?" charset="utf-8"></script><script>window.alreadyProcessedMarkdeep||(document.body.style.visibility="visible")</script>'
STATUS_ONLY_FAILED = {
    'planned': False,
    'paused': False,
    'inProgress': False,
    'completed': False,
    'aborted': False,
    'failed': True,
}
STATUS_ALL = {
    'planned': True,
    'paused': True,
    'inProgress': True,
    'completed': True,
    'aborted': True,
    'failed': True,
}

# Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
streamhdlr = logging.StreamHandler(sys.stdout)
logger.addHandler(streamhdlr)
streamhdlr.setLevel(logging.INFO)
formatter1 = logging.Formatter('{lineno}**{message}** at{asctime}|{name}', style='{')
formatter2 = logging.Formatter('{name}---> {message}', style='{')
formatter3 = logging.Formatter('{asctime} | {funcName}[{lineno}] | {levelname} | {message}', style='{')
streamhdlr.setFormatter(formatter3)


# https://docs.xebialabs.com/xl-release/10.1.x/rest-docs/

def u_parse_xlr_id(id: str, part: str, last_part_only=False):
    if part not in ['Release', 'Phase', 'Task']:
        logger.error(f"(I am) unable to get {part} from id: it's not implemented.")
        sys.exit(1)
    # Applications/Folder421083452/Folder857770573/Folder936654366/Folderd0ab72c045284146a36e1bfbb9142730
    # /Folder38afa3c9e26418abfcc9cacccf3cf14/Release0e4d6f626ff24d51acb64e1d4952a27e/Phasef593d0c0634241cbb7a4e3f8db1162cf
    # /Task9b0c95253e644023a2255f5984e37152/Taskbd8fb48095d9409a921c008489b8ad06

    if id.find("-") > 0:
        id += "-"
    else:
        id += "/"
    retval = re.sub(rf"^(.*[-\/]{part}[^-\/]*).*", r"\1", id)
    if last_part_only:
        retval = re.sub(rf".*[-\/]({part}[^-\/]*).*", r"\1", id)

    return retval


class Server:
    def __init__(self, user: str, pw: str, url: str = ""):
        self.url = url
        self.session: requests.sessions.Session = requests.Session()
        self.session.auth = (user, pw)
        self.session.verify = False
        self.session.headers.update({
            # "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "keep-alive",

            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "hu-HU,hu;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Type": "application/json",
            "Content-Type": "application/json;charset=utf-8",
            "Host": "xlrelease.rbgooe.at",
            "Origin": "https://xlrelease.rbgooe.at",
            "Referer": "https://xlrelease.rbgooe.at/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:100.0) Gecko/20100101 Firefox/100.0",
            "X-HTTP-Auth-Override": "true",
        })

        logger.info(f"Connecting to {self.url} with user {user}...")
        response: Response = self.session.post(
            url=f"{self.url}/login",
            data=json.dumps({"username": user, "password": pw})
        )
        response.raise_for_status()
        logger.info(f"Connection OK.")

        self.session.headers.update(
            self.session.cookies.get_dict()
        )
        self.session.headers.update({
            "X-XSRF-TOKEN": self.session.cookies.get("XSRF-TOKEN", "")
        }
        )

        # - "Cookie": "JSESSIONID=node01tg2ugu6p5oqq11vwskq1crnqp818.node0; XSRF-TOKEN=40880eda-3f56-4fbf-a6fe-9ad9f9c65fac",
        c = ""
        for k, v in self.session.cookies.get_dict().items():
            c += f"{k}={v}; "
        self.session.headers.update(
            {"Cookie": c}
        )

        logger.debug("Session header:")
        for k in sorted(self.session.headers.keys()):
            logger.debug(f" {k}: '{self.session.headers[k]}'")

        if self.session is None:
            logger.error("Connection not initialised, aborting.")
            sys.exit(1)

        # self.session.get('https://httpbin.org/headers', verify=False)


class Release:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id_long = self.id
        self.id = u_parse_xlr_id(self.id_long, "Release", last_part_only=True)
        self.active_tasks = self.get_active_tasks()
        pass

    def get_active_tasks(self):
        url = f"{server.url}/api/v1/releases/{self.id}/active-tasks"
        response: Response = server.session.get(
            url=url)
        response.raise_for_status()
        resp_json = response.json()
        tasks = [Task(**x) for x in resp_json]
        return tasks

    @staticmethod
    def get_md_from_releases(releases: list, title="Some releases"):

        output_md = f"## {title}\n"

        if len(releases) > 0:
            # Table generation
            rows = []
            rows.append(['Release', 'Status', 'Active Phase', 'Active task', 'Task type'])
            for release in releases:
                v1 = " [{}]({})".format(re.sub(r"\d*A\d*-", r"", release.title), release.url)
                v2 = release.status
                v3 = "-"
                v4 = "-"
                v5 = "-"
                for active_task in release.active_tasks:
                    v3 = active_task.phase.title
                    v4 = active_task.title
                    v5 = active_task.type
                pass
                rows.append([v1, v2, v3, v4, v5])
            output_md += generate_markdown(table_from_string_list(rows, Alignment.LEFT)) + "\n"
        else:
            output_md += "No releases found.\n\n"

        return output_md

    @staticmethod
    def search_releases(title: str, tags: List[str], statuses: dict, exceptPhases: List[str] = []):
        l_run_start = float(time.time())
        data = {
            'title': title,
            'tags': tags,
            'failed': statuses.get('failed', True),
            'planned': statuses.get('planned', True),
            'paused': statuses.get('paused', True),
            'inProgress': statuses.get('inProgress', True),
            'completed': statuses.get('completed', True),
            'aborted': statuses.get('aborted', True)
        }
        f = {k: v for (k, v) in statuses.items() if v}
        logger.info(
            "search_releases(title='{}', tags:{}, statuses: [{}])".format(title, tags, ", ".join(f.keys())))
        releases: List[Release] = []
        page = 0
        while True:
            response: Response = server.session.post(
                # /releases/search?page=0&resultsPerPage=1&pageIsOffset=false
                url=f"{server.url}/releases/search?page={page}&resultsPerPage=15&pageIsOffset=false",
                data=json.dumps(data))
            response.raise_for_status()
            resp_json = response.json()
            new_releases = [Release(**x) for x in resp_json['cis']]
            if len(new_releases) == 0:
                break
            new_releases_len_unfiltered = len(new_releases)
            new_releases = [x for x in new_releases if x.currentPhase not in exceptPhases]
            logger.info(f"{len(new_releases)} found.")
            new_releases_len_filtered = len(new_releases)
            if new_releases_len_unfiltered != new_releases_len_filtered:
                logger.info("{} releases filtered out: their phases are not important for us.".format(
                    new_releases_len_unfiltered - new_releases_len_filtered))
            releases = releases + new_releases
            page += 1
        l_run_end = float(time.time())
        dt = 1000.0 * (l_run_end - l_run_start)
        if len(releases) == 0:
            logger.info(f"No release found.")
        elif len(releases) == 1:
            logger.info("One release found. ({}ms/release)".format(int(dt)))
        else:
            logger.info(
                "{} releases found {}ms/release.".format(len(releases), int(dt / len(releases))))

        for release in releases:
            release.url = f"{server.url}/#/releases/{release.id_long}"
            release.server = server
        return releases

    def __str__(self):
        retval = f"Release: [{self.title}]\n"
        retval += f" url: {self.url}\n"
        retval += f" status: {self.status}\n"
        retval += f" Current phase: {self.currentPhase}\n"

        return retval


class Phase:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @staticmethod
    def get_phase_by_id(phase_id_long):
        url = f"{server.url}/api/v1/phases/{phase_id_long}"
        response: Response = server.session.get(
            url=url)
        response.raise_for_status()
        resp_json = response.json()
        phase = Phase(**resp_json)
        return phase


class Task:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id_long = self.id

        self.id = u_parse_xlr_id(self.id_long, "Task")
        self.phase_id = u_parse_xlr_id(self.id_long, "Phase")
        self.release_id = u_parse_xlr_id(self.id_long, "Release", last_part_only=True)
        self.phase = Phase.get_phase_by_id(self.phase_id)
        pass

    def __str__(self):
        retval = f"Task: {self.phase.title} / {self.title}\n"
        retval += f" Status: {self.status}\n"
        return retval


def get_env_var(var_name: str) -> str:
    if var_name not in os.environ:
        logger.error(f"Please set {var_name} as environment variable. Aborting.")
        sys.exit(1)
    return os.environ.get(var_name, None)


xlr_servers = {
    "atz": "https://xlrelease-atz.rbgooe.at",
    "prod": "https://xlrelease.rbgooe.at"
}

server = Server(url=xlr_servers['prod'], user=get_env_var('XLR_USER'), pw=get_env_var('XLR_PASSWORD'))


def collecting_info(release_title):
    releases = {
        'releases_tag_release': Release.search_releases(title=release_title,
                                                        tags=["drb", "release"],
                                                        statuses=STATUS_ONLY_FAILED
                                                        ),
        'releases_tag_rollout': Release.search_releases(title=release_title,
                                                        tags=["drb", "rollout"],
                                                        statuses=STATUS_ONLY_FAILED,
                                                        exceptPhases=["tstux - Qualitycheck"]
                                                        ),
        'releases_tag_applikationstests': Release.search_releases(title=release_title,
                                                                  tags=["drb", "applikationstests"],
                                                                  statuses=STATUS_ONLY_FAILED,
                                                                  exceptPhases=["TSTUX"]
                                                                  )
    }

    return releases


def generate_report(release_title: str, out_dir: str, keep_files=True):
    l_ts_start = time.time()
    now = datetime.now()
    now_yyyymmdd_hhmm = now.strftime("%Y.%m.%d %H:%M")
    now_yyyymmdd_hhmm_ = now.strftime("%Y%m%d_%H%M")
    releases = collecting_info(release_title=release_title)

    output_md_header = f"# {release_title}\n\n"
    output_md = output_md_header
    output_md += Release.get_md_from_releases(releases['releases_tag_release'],
                                              title="Failed items with tag: [release]")
    output_md += Release.get_md_from_releases(releases['releases_tag_applikationstests'],
                                              title="Failed items with tag: [applikationstests]")
    output_md += Release.get_md_from_releases(releases['releases_tag_rollout'],
                                              title="Failed items with tag: [rollout]")

    output_md += f"Time of generation: {now_yyyymmdd_hhmm}\n"

    output_md_html = output_md
    output_md_html += "\n"
    output_md_html += MARKDEEP_FOOTER

    file_name = f"{out_dir}/{release_title}_LATEST.md"
    with open(file_name, "w", encoding="utf-8") as FILE:
        FILE.write(output_md)
    if keep_files:
        shutil.copyfile(file_name, f"{out_dir}/{release_title}_{now_yyyymmdd_hhmm_}.md")

    file_name = f"{out_dir}/{release_title}_LATEST.md.html"
    with open(file_name, "w", encoding="utf-8") as FILE:
        FILE.write(output_md_html)
    if keep_files:
        shutil.copyfile(file_name, f"{out_dir}/{release_title}_{now_yyyymmdd_hhmm_}.md.html")
    l_ts_end = time.time()
    logger.info("generate_report(): returning after {}seconds.".format(int(l_ts_end - l_ts_start)))


def main():
    parser = argparse.ArgumentParser(usage="usage: TODO")
    parser.add_argument(
        "-o", "--output-dir",
        dest="out_dir", default=os.path.curdir,
        help="Output dir for the report files."
    )
    parser.add_argument(
        "-k", "--keep-files",
        action="store_true",
        dest="keep_files",
        default=False,
        help="Keep old files."
    )
    parser.add_argument(
        "-r", "--release-title",
        dest="release_title",
        required=True,
        help="The title of the release you want to report."
    )
    parser.add_argument(
        "--hours",
        dest="run_hours",
        default=1.0,
        type=float,
        help="Run for x hours. Default: 1"
    )
    parser.add_argument(
        "-w", "--wait",
        dest="call_every_min",
        default=3,
        type=int,
        help="Collect data every x minutes. Default: 1"
    )
    args = vars(parser.parse_args())

    # if options.locale and not options.encoding:
    #     parser.error("if --locale is specified --encoding is required")
    #     sys.exit(1)

    if not args['release_title']:  # if filename is not given
        logger.error('Release title not given.')
        print(parser.usage)
        sys.exit(1)

    if not os.path.exists(args['out_dir']):
        logger.error(f"Directory '{args['out_dir']}' does not exist, aborting.")
        sys.exit(1)

    logger.info(f"Run parameters:")
    logger.info(f" - Collecting info every {args['call_every_min']} minutes.")
    logger.info(f" - Keep files historical: {args['keep_files']}")
    logger.info(f" - Output directory: {args['out_dir']}")
    logger.info(f" - Release to be monitored: {args['release_title']}")
    logger.info(f" - Run time: {args['release_title']}")

    # "220519A00"
    run_end = int(time.time()) + args['run_hours'] * 60 * 60
    while True:
        next_run = int(time.time()) + args['call_every_min'] * 60
        if int(time.time()) > run_end:
            break
        generate_report(release_title=args['release_title'], keep_files=args['keep_files'], out_dir=args['out_dir'])
        sleep_time_s = int(time.time()) - next_run
        if next_run > run_end:
            break
        if sleep_time_s > 0:
            logger.info(f"Waiting {sleep_time_s} seconds...")
            time.sleep(sleep_time_s)  # Sleep for x seconds
        else:
            logger.warning(f"Wait time too low. ({sleep_time_s})")


if __name__ == '__main__':
    main()
    main()
