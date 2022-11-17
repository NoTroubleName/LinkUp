from json.decoder import JSONDecodeError
import os
import subprocess
import platform
from datetime import datetime as date
import sys
import info_handler
from datenbank import Blob, Datenbank, File, Jewel


class Backup:
    current_source_path = None
    current_date_time = date.now()
    current_date_time_formatted = current_date_time.strftime("%Y-%m-%d-%H-%M")
    new_backup_location = f"backup-{current_date_time_formatted}"
    device_name = platform.node()


    def __init__(self, jewel_path_list, destination, testcase=False):
        self.jewel_path_list = jewel_path_list
        self.destination = destination
        self.db = Datenbank()
        if(testcase):
            self.device_name = "testCases"
        fullbackup_name = "fullBackup" + self.device_name

    def initialize_backup(self):        
        # to minimize work, first check if these paths even exists, then continue
        tmp = self.filter_non_existing_paths(self.jewel_path_list)

        diff_backup_sources = self.db.check_which_jewel_sources_exist(tmp, self.device_name)
        # filter out everything, that is in diff_backup already
        full_backup_sources = [e for e in tmp if e not in diff_backup_sources]

        # execute,when not empty
        if diff_backup_sources:
            self.execute_backup(diff_backup_sources)

        # execute, when not empty
        if full_backup_sources:
            self.execute_fullbackup(full_backup_sources)


    def execute_backup(self, jewel_sources):
        print("Creating differential backup")
        leave_out_sources = []
        differential_backup_name = f"diff-{date.now().strftime('%d-%m-%Y-%H-%M')}"
        old_jewels = self.db.get_fullbackup_paths(jewel_sources)
        backup_sources_for_r_sync = " ".join(jewel_sources)

        subprocess_return = subprocess.Popen(f"rsync -aAXn {self.excluding_data()} --out-format='%n' "
                                             f"--compare-dest={self.destination}/{self.fullbackup_name} {backup_sources_for_r_sync} "
                                             f"{self.destination}/{differential_backup_name}",
                                             shell=True,
                                             stdout=subprocess.PIPE)
        output = subprocess_return.stdout.read()
        output = output.decode('utf-8')
        print(output)
        output_array = output.splitlines()
        insert_results = self.read_files_and_jewel_from_rsync_output(output_array, jewel_sources,
                                                    f"{self.destination}/{differential_backup_name}",
                                                    self.destination + "/" + self.fullbackup_name)
        
        print(insert_results)
        for result in insert_results:
                leave_out_sources.append(result[2])

        
        subprocess.Popen(f"rsync -aAX {self.excluding_data()} --out-format='%n' "
                                             f"--compare-dest={self.destination}/{self.fullbackup_name} {backup_sources_for_r_sync} "
                                             f"{self.destination}/{differential_backup_name}",
                                             shell=True,
                                             stdout=subprocess.PIPE)

        for result in insert_results:
                self.set_hardlink(result[0], result[1])


        print(leave_out_sources)


    def execute_fullbackup(self, jewel_sources):
        print("Creating full backup")

        jewel_path_list_string = self.list_to_string(jewel_sources)
        subprocess_return = subprocess.Popen(f'rsync -aAX {self.excluding_data()} --out-format="%n" '
                                             f'{jewel_path_list_string} '
                                             f'{self.destination}/{self.fullbackup_name}',
                                             shell=True,
                                             stdout=subprocess.PIPE)
        output = subprocess_return.stdout.read()
        output = output.decode('utf-8')
        output_array = output.splitlines()
        self.read_files_and_jewel_from_rsync_output(output_array, jewel_sources,
                                                    f"{self.destination}/{self.fullbackup_name}",
                                                    self.destination + "/" + self.fullbackup_name)


    def list_to_string(self, string_list) -> str:
        formatted_string = " ".join(string_list)
        return formatted_string


    def filter_non_existing_paths(self, paths) -> list[str]:
        for jewel_path in paths:
            if not (os.path.exists(jewel_path)):
                paths.remove(jewel_path)
        return paths


    def read_files_and_jewel_from_rsync_output(self, output_array, jewel_sources, store_destination_body,
                                               fullbackup_store_destination_body) -> list[str|bool]:
        result = []
        if output_array == []:
            print("result ist leer")
            exit
        for line in output_array:
            if line.endswith('/'):
                self.current_source_path = line

                # check wether path is now the jewel
                for jewel_path in jewel_sources:

                    # stripping and splitting is needed, since comparison does not work otherwise
                    if jewel_path.rsplit('/', 1)[1].strip("/") == line.strip("/"):
                        jewel = Jewel(0, None, date.today(), jewel_path, self.device_name,
                                      f'{fullbackup_store_destination_body}/{line.strip("/")}')
                        break
                    # if top layer of jewel was not changed, the jewel would not be in line.strip... so we need to split and get the first folder
                    elif jewel_path.rsplit('/', 1)[1].strip("/") == line.split("/")[0]:
                        jewel = Jewel(0, None, date.today(), jewel_path, self.device_name,
                                      f'{fullbackup_store_destination_body}/{line.strip("/")}')

            else:
                # get only the working dir without the jewel(because line inherits the jewel)
                working_dir = jewel_path.rsplit('/', 1)[0]
                file_object = info_handler.get_metadata(working_dir + '/' + line)
                # Erstellt Array erstes element vor letztem Slash, zweites Element nach dem Slash
                file_name = line.rsplit('/', 1)[1]
                blob = Blob(0, 0, file_object.f_hash, (f'{file_object.f_size}_{file_object.f_hash}'),
                            file_object.f_size,
                            self.current_date_time, file_object.modify, 0, file_name,
                            working_dir + "/" + line, f'{store_destination_body}/{line}')

                file = File(0, [blob], file_object.birth)
                datenbank = Datenbank()
                db_answer = datenbank.add_to_database(jewel, file, self.device_name)

                if db_answer is not True:
                    result.append((db_answer,blob.store_destination,working_dir + "/" + line))

        return result


    def excluding_data(self):
        config = info_handler.get_json_info()
        return_list = []
        for element in config['blacklist']['directories'] + config['blacklist']['files']:
            return_list.append(f'--exclude \'{element}\'')
        for extension in config['blacklist']['extensions']:
            return_list.append(f'--exclude \'*{extension}\'')
        return ' '.join(return_list)


    def set_hardlink(self, source_path, destination_path):
        #TODO hardlink action must be inserted here
        print("------------------------------------")
        print("Die Datei die am Ort \n" + destination_path + "\n abgespeichert werden würde muss zu einem hardlink zum Pfad \n"+ source_path 
        + "\n germacht werden. ")
        #create hardlink
        #source_path = '\'' + source_path + '\''
        #destination_path = '\'' + destination_path + '\''+
        
        subprocess.run(f"tree -a {'/home/mirco/backuptarget'}", shell=True)
        d_path = os.path.dirname(os.path.abspath(destination_path))
        subprocess.run(f"ls {d_path}", shell=True)
        print(d_path)
        os.remove(destination_path)
        print("BRÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜÜ", source_path, destination_path)
        subprocess.run(f'ln {source_path} {destination_path}', shell=True)
        #os.link(source_path, destination_path)

        pass
