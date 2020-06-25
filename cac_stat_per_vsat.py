import os, sys, time, collections, re, telnetlib


#Class for parsed output
class parsCli():                                                #Obj of this class will take argument of parsing map (fields:parsing regexp), with methods to prase text based on this map providing dict: 'field':'value'

        def __init__(self, parsplan):                           #parsplan is a map for parsing, namely a dictionary {'field_name': re.compile() expression}
                self.parsplan = parsplan
                self.aggCsv = {'headline':'', 'data':''}        #Dictionary used to store parsed output {'filed_name':'output'}

        def parseTxt(self, text, entry_id=''):                  #parseTxt method takes text to parse and an entry_id(optional)
                pars_out = collections.OrderedDict()            #parsOut is Ordered dictionary, to store parsed output
                pars_out['entry_id'] = entry_id
                for line in text.split('\n\r'):
                        for pars in self.parsplan:              # Here we are going over all the lines and checking if it fit parsing expressions
                                if self.parsplan[pars].search(line):
                                        parsed_value = self.parsplan[pars].search(line)
                                        pars_out[pars] = parsed_value.group(1)
                                        break
                return (pars_out)

        def aggrCsv(self, pars_out, datetime=''):               #Method to aggregate pars_out to a string(csv), if datetime is not supplied, it will take current datetime in GMT
                if not datetime: 
                        datetime = time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime())
                headline = 'datetime,'+','.join(i for i in pars_out)+'\n'
                csvline = datetime + ',' + ','.join(pars_out[i] for i in pars_out)+'\n'
                if not self.aggCsv['headline']:
                        self.aggCsv['headline'] = headline
                self.aggCsv['data'] += csvline

                return (self.aggCsv)

        def writeCsv(self, fname, headline=False, data=True, clear_aggr = True):    #Method that writes aggregated csv string to a file
                with open(fname, 'a+') as file:
                        if (headline or os.stat(fname).st_size == 0): file.write(self.aggCsv['headline'])  #Headline will be written if it explicitly requested or in case file is empty
                        if data: file.write(self.aggCsv['data'])                                           #In case argument data=False, data will be not written (only headline)
                if clear_aggr:                                                                             #clear_aggr argument used in casde there is a need to flush self.aggCsv dict after file has been written
                        self.aggCsv = {'headline':'', 'data':''}


class telnetCli():                   #Method used to send/receive telnet command/output

        def __init__(self, host):
                self.HOST = host
                self.WAIT_TIMEOUT = 0.2
                self.conn = telnetlib.Telnet(self.HOST)

        def sendCommand(self, command, timeout=0.01, by_sym=False):     #by_sym argument used when theer is a need to send command by symbol (one by one), instead of sending entire string
            command += "\r\n"    
            if by_sym:
                for ch in command:
                    self.conn.write(ch.encode('ascii'))
                    time.sleep(timeout)
            else:
                self.conn.write(command.encode('ascii'))
            
            time.sleep(self.WAIT_TIMEOUT)     #wait for device to generate output
            return True

        def readOutput(self):
            return self.conn.read_very_eager()


def parse_bb(bb_links):         #Function to parse DPS 'bb links' command and build an list of VSAT IDs
        vsat_ids = []
        for line in bb_links.split('\n\r'):
                if re.match('^\|\W(\d*)\W\|', line):
                        bb_link = re.match('^\|\W(\d*)\W\|', line)
                        vsat_ids.append(bb_link.group(1))
        return (vsat_ids)



def main():

    #Constants
    DPS = '' #- only if you want to bypass autodiscovery
    HSP = '' #- only if you want to bypass autodiscovery
    FILENAME = 'vsat_cac_stat.csv'

    if not (DPS and HSP):       #Discovering IP of DPS and HSP
        with open('/etc/sysconfig/network-scripts/ifcfg-br17','r') as file:
            domain=re.search('.*IPADDR=\d*\.\d*\.(\d*).*',file.read())
            DPS = '172.17.%s4.1' % domain.group(1)[1]
            HSP = '172.17.%s2.1' % domain.group(1)[1]        

    try:
        if sys.argv[1]: FILENAME = str(sys.argv[1])+'.csv'
    except:
        pass

    print('\nPreparing parsing map')
    # Below parsing agenda is build, a dictionary {name_of_fiels : parsing_regexp}
    pmap = {}
    types = ['new','modify','change_to_rob','change_to_eff']

    pars = {'new':r'\W*Number.*new.*-\W\b@\b\W*(\d*)',
                    'modify':r'\W*Number.*modify.*-\W\b@\b\W*(\d*)',
                    'change_to_rob':r'\W*Number.*change.*robust.*-\W\b@\b\W*(\d*)',
                    'change_to_eff':r'\W*Number.*change.*efficient.*-\W\b@\b\W*(\d*)'}
    fields = ['NO_CAUSE', 'BACKHAULING_LIMIT', 'CBR_LIMIT', 'NO_FREE_BW', 'NO_VOIP_ALLOC_OPTION', 'GLOBAL_BW_LIMIT', 'MPN_MIR', 'OUT_OF_VSAT_CAPACITY', 'NO_FREE_BW_FOR_VOIP']

    for tip in types:
            for filed in fields:
                    pmap[tip+'_'+filed] = re.compile(pars[tip].replace('@',filed))

    bh_rejects = parsCli(pmap)


    #Getting list of VSATs from DPS
    dps_telnet = telnetCli(DPS)
    print ('Creating list of VSAT IDs')
    dps_telnet.sendCommand('bb links')
    bb_links = dps_telnet.readOutput()
    vsat_ids = parse_bb(bb_links)
    print ('Got '+str(len(vsat_ids))+' VSATs\n')

    hsp_telnet = telnetCli(HSP)
    date = time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime())

    for vsat_id in vsat_ids:
            print ('-> Fetching VSAT: ' + vsat_id)
            hsp_telnet.sendCommand('stat cac link '+ vsat_id, by_sym=True)
            hsp_out = hsp_telnet.readOutput()
            parsed_hsp_out = bh_rejects.parseTxt(hsp_out,entry_id=vsat_id)
            bh_rejects.aggrCsv(parsed_hsp_out, datetime = date)

    print('\nSaving data to the csv file: '+FILENAME)
    bh_rejects.writeCsv(FILENAME)
    print('Completed. Fetched: '+str(len(vsat_ids))+' VSATs\n')


if __name__ == "__main__":
    main()