
import pandas as pd
import matplotlib.pyplot as plt
import scipy.fftpack
import numpy as np
from scipy.fft import fft, ifft

#ROTOR

# material
steel = rs.Material(name="Steel", rho=7810, E=211e9, G_s=81.2e9)
steel.save_material()

#shaft
L =   [0.018, 0.037, 0.045, 0.005, 0.03, 0.005, 0.065, 0.04, 0.06]
i_d = [0,    0,    0,    0,    0,   0,   0,   0,   0]
o_d = [0.010, 0.010, 0.010, 0.010, 0.010, 0.010, 0.010, 0.010, 0.010]
shaft_elements = [
    rs.ShaftElement(
        L=l,
        idl=idl,
        odl=odl,
        material=steel,
        shear_effects=True,
        rotary_inertia=True,
        gyroscopic=True,
    )
    for l, idl, odl in zip(L, i_d, o_d)
]
shaft_elements

#disks
n_list = [4, 5, 6]
width_list = [0.01, 0.01, 0.01]
i_d_list = [0.01, 0.01, 0.01]
o_d_list = [0.024, 0.084, 0.024]
N = len(n_list)
disk_elements = [
    rs.DiskElement.from_geometry(
        n=n_list[i],
        material=steel,
        width=width_list[i],
        i_d=i_d_list[i],
        o_d=o_d_list[i],
    )
    for i in range(N)
]
disk_elements

#ballbearing - https://www.skf.com/br/products/rolling-bearings/ball-bearings/deep-groove-ball-bearings/productid-16002-2Z
n_balls= 9
d_balls = 0.0065
fs = 500.0
alpha = np.pi / 6

ballbearing1 = rs.BallBearingElement(
    n=1,
    n_balls=n_balls,
    d_balls=d_balls,
    fs=fs,
    alpha=alpha,
    tag="ballbearing1",
)
ballbearing2 = rs.BallBearingElement(
    n=8,
    n_balls=n_balls,
    d_balls=d_balls,
    fs=fs,
    alpha=alpha,
    tag="ballbearing2",
)
ballbearings = [ballbearing1, ballbearing2]


#pointmass
#p0 = rs.PointMass(n=5, m=2)
#p0.M()

#rotor
rotor1 = rs.Rotor(shaft_elements, disk_elements, ballbearings)
print("Rotor total mass = ", np.round(rotor1.m, 2))
print("Rotor center of gravity =", np.round(rotor1.CG, 2))


#time_response

speed = 3590/60 
size = 40
t = np.linspace(0, 5, size)
F = np.ones((size, rotor1.ndof))
tr = rotor1.time_response(speed, F, t) 

print (type(tr[1][1]))
print (type(tr[0]))

print (len(tr[1][1]))
print (len(tr[0]))

print (tr[1][1])
print (tr[0])

plt.plot(tr[0], tr[1][1])
plt.show

#FFT


#-----------------       FIELD-DATA      -----------------------

dt = input('Qual o intervalo de tempo dos dados, em milisegundos?')

''' function "field_data(file, sheet_name=0)" reads a xls file path with field data content (the file path may be named "field_data_si.xls" for SI units), ZIPs the vectors of time response data putting together time and displacement values with may be not exactly sampled and sample the whole data into equally sampled intervals.

file: str
    path to the file containing field data.
    
sheet_name : int or str, optional
    position of the sheet in the file (starting from 0) or its name
    
how to call?
EX.:
field_data_file = "field_data_si.xls"
time_response_data = field_data(file=field_data_file,  sheet_name = 'time_response')
print(time_response_data)
'''

'''def field_data(file, sheet_name=0):   
    if sheet_name == 'time_response':
        time_response_data = pd.read_excel(field_data_file,'time_response')
        time = time_response_data.time
        displacement = time_response_data.displacement
        time_response = zip(time,displacement)
        plt.plot(time, displacement)
        return list(time_response)    
   '''   

field_data_file = "field_data_si.xls"

time_response_data = pd.read_excel(field_data_file,'time_response')
time = time_response_data.time
displacement = time_response_data.displacement
#plt.plot(time, displacement)
print(time_response_data)


time_response_data = time_response_data.assign(
time=pd.to_datetime(time_response_data.time, unit='ms')
).resample(str(dt)+'ms', on='time').mean().reset_index().ffill()

print(time_response_data)
displacement = time_response_data.displacement
time = time_response_data.time
#plt.plot(time[range(len(displacement))], displacement)

displacement = np.array(displacement)
y = fft(displacement)
x = 60*scipy.fftpack.fftfreq(y.size, float(dt)/1000)

print (type(x))

plt.xlabel('Freq (CPM)')
plt.ylabel('FFT Amplitude |X(freq)|')
plt.plot(np.abs(x), np.abs(y))
plt.show()

