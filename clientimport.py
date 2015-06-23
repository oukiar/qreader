
#parse stuff
from parse_rest.connection import register, ParseBatcher
from parse_rest.datatypes import Object
from parse_rest.user import User

import time

#parse initialization
register("XEPryFHrd5Tztu45du5Z3kpqxDsweaP1Q0lt8JOb", "PE8FNw0hDdlvcHYYgxEnbUyxPkP9TAsPqKvdB4L0")
     
ClientsTest = Object.factory("Clients")
     

lines = open("Clients.csv").readlines()

clientslist = []

counter = 0

for line in lines:
    #print lines.index(line)
    client = ClientsTest()
    
    try:
        name, email, company, country = line.split(",")
    except:
        name = line.split('"')[0]
        fooname, email, company, country, morefoo = line[len(name)+2:].split(",")
        
    client.Name = name
    client.Email = email
    client.Company = {"__type": "Pointer", "className": "Companies", "objectId": "AgViN0JqQq"}
    client.Key = company
    client.Country = country
    #client.save()
    
    clientslist.append(client)
    
    print email
    
    counter += 1
    
    if(counter == 20):
    
        batcher = ParseBatcher()
        batcher.batch_save(clientslist)
        clientslist = []

        print "Esperando algunos segundos"

        #esperar un poco
        time.sleep(.1)
        
        counter=0
        
        print "Trabajando ..."
    
print str(len(lines)) + " lines analized"
