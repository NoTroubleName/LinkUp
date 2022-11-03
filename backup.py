import os
import subprocess
import platform
from datetime import datetime as date

import info_handler
from datenbank import Blob, Datenbank, File, Jewel


class Backup:

    current_source_path = None
    current_date_time = date.now()
    current_date_time_formatted = current_date_time.strftime("%d-%m-%Y-%H-%M")
    new_backup_location = f"backup-{current_date_time_formatted}"

    def __init__(self, filepath, jewel_path_list):
        self.filepath = filepath
        self.jewel_path_list = jewel_path_list

    def initialize_backup(self):
        db = Datenbank()

        #to minimize work, first check if these paths even exists, then continue
        tmp = self.filter_non_existing_paths(self.jewel_path_list)

        diff_backup_sources = db.check_which_jewel_sources_exist(tmp, platform.node())
        full_backup_sources = [e for e in tmp if e not in  diff_backup_sources]

        #execute,when not empty
        if diff_backup_sources:
            self.execute_backup(diff_backup_sources)

        #execute, when not empty
        if full_backup_sources:
            self.execute_fullbackup(full_backup_sources)

    def execute_backup(self, jewel_sources):
        print("Creating differential backup")

    def execute_fullbackup(self, jewel_sources):
        print("Creating full backup")

        jewel_path_list_string = self.list_to_string(jewel_sources)
        subprocess_return = subprocess.Popen(f'rsync -aAXn --out-format="%n" {jewel_path_list_string} '
                                             '/home/gruppe/backupTest/fullBackup',
                                             shell=True, cwd='/home/gruppe/backupTest',
                                             stdout=subprocess.PIPE)
        output = subprocess_return.stdout.read()
        output = output.decode('utf-8')
        output_array = output.splitlines()
        
        for line in output_array:                     
            if line.endswith('/'):
                self.current_source_path = line

                #check wether path is now the jewel
                for jewel_path in jewel_sources:

                    #stripping and splitting is needed, since comparison does not work otherwise
                    if jewel_path.rsplit('/', 1)[1].strip("/") == line.strip("/"):
                        jewel = Jewel(0, None, date.today(),self.filepath + '/' + line.strip('/'), platform.node())
                        break

            else:
                file_object = info_handler.get_metadata(self.filepath + '/' + line)
                # Erstellt Array erstes element vor letztem Slash, zweites Element nach dem Slash
                file_name = line.rsplit('/', 1)[1]
                blob = Blob(0, 0, file_object.f_hash, file_object.name, file_object.f_size,
                            self.current_date_time, file_object.modify, file_object.modify, 0, file_name,
                            self.current_source_path, self.new_backup_location)
                file = File(0, [blob], file_object.birth)
                datenbank = Datenbank()
                result = datenbank.add_to_database(jewel, file, platform.node())
                print(result)

    def list_to_string(self, string_list):
        formatted_string = " ".join(string_list)
        return formatted_string

    def filter_non_existing_paths(self, paths):
        for jewel_path in paths:
            if not(os.path.exists(jewel_path)):
                paths.remove(jewel_path)
        return paths