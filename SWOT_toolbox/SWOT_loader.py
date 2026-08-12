
from netCDF4 import Dataset 
import numpy as np


class SWOT_loader:
    '''
    This class is made to load the SWOT raster NetCDF file, explore and extract data.
    '''
    def __init__(self, file_path): 
        self.file_path = file_path
        self.dataset = Dataset(file_path, 'r')
                
    def explore_data(self):
        """ Display available variables in the NetCDF file """
        print("Available variables:")
        for var_name in self.dataset.variables:
            var = self.dataset.variables[var_name]
            dims = var.dimensions
            shape = var.shape
            print(f"- {var_name}: shape={shape}, dimensions={dims}")
            
        print("\nGlobal attributes:")
        for attr in self.dataset.ncattrs():
            print(f"- {attr}: {getattr(self.dataset, attr)}")


    
    def contains(self, lat, lon):
        """
        Check if a given point is inside the domain of the NetCDF file

        Parameters:
        -----------
        lat : float
            Latitude of the point
        lon : float
            Longitude of the point

        Returns:
        --------
        bool
            True if the point is inside the domain, False otherwise
        """
        lon_min = float(self.dataset.geospatial_lon_min)
        lon_max = float(self.dataset.geospatial_lon_max)
        lat_min = float(self.dataset.geospatial_lat_min)
        lat_max = float(self.dataset.geospatial_lat_max)

        return (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max)
    
    def get_variable(self, variable_name):
        """
        Get a variable from the dataset by name
        
        Parameters:
        -----------
        variable_name : str
            Name of the variable to retrieve
            
        Returns:
        --------
        array-like
            Data for the requested variable
            
        Raises:
        -------
        KeyError
            If the requested variable doesn't exist in the dataset
        """
        try:
            return self.dataset.variables[variable_name][:]
        except KeyError:
            available_vars = list(self.dataset.variables.keys())
            raise KeyError(f"Variable '{variable_name}' not found. Available variables: {available_vars}")

    def get_array_and_coords(self, var_name):
        """
        Return a 2D or 3D variable and its associated coordinates (longitude and latitude)
        """
        var_data = self.get_variable(var_name)
        
        # Determine coordinate variable names
        coord_vars = {
            'lon': ['longitude', 'lon', 'x'],
            'lat': ['latitude', 'lat', 'y']
        }
        
        lons = None
        lats = None
        
        # Try to find coordinate variables
        for lon_var in coord_vars['lon']:
            if lon_var in self.dataset.variables:
                lons = self.get_variable(lon_var)
                break
                
        for lat_var in coord_vars['lat']:
            if lat_var in self.dataset.variables:
                lats = self.get_variable(lat_var)
                break
        
        if lons is None or lats is None:
            print("Warning: Could not find longitude/latitude variables")
            
        return var_data, lons, lats
    
    def extract_point_val(self, var_name, lon, lat):
        """
        Extract a variable value at a given longitude/latitude point
        
        Parameters:
        -----------
        var_name : str
            Name of the variable to extract
        lon : float
            Longitude of the point
        lat : float
            Latitude of the point
            
        Returns:
        --------
        float
            Value of the variable at the specified point
        """
        # Get the variable data
        var_data = self.get_variable(var_name)
        
        # Find coordinate variables
        lon_vars = ['longitude', 'lon', 'x']
        lat_vars = ['latitude', 'lat', 'y']
        
        lon_var = None
        lat_var = None
        
        for var in lon_vars:
            if var in self.dataset.variables:
                lon_var = var
                break
                
        for var in lat_vars:
            if var in self.dataset.variables:
                lat_var = var
                break
        
        if lon_var is None or lat_var is None:
            raise ValueError("Could not find longitude/latitude variables in the dataset")
        
        # Get coordinate data
        lons = self.get_variable(lon_var)
        lats = self.get_variable(lat_var)
                
        # Handle different coordinate dimensions
        if lons.ndim == 1 and lats.ndim == 1:
            # Regular grid (1D coordinates)
            lon_idx = np.abs(lons - lon).argmin()
            lat_idx = np.abs(lats - lat).argmin()
            
            
            # Check variable dimensions
            if var_data.ndim == 2:
                try:
                    # Try lat, lon order (common in climate data)
                    z = var_data[lat_idx, lon_idx]
                except IndexError:
                    # Try lon, lat order
                    z = var_data[lon_idx, lat_idx]
            elif var_data.ndim == 3:
                # For 3D variables (e.g., with time)
                try:
                    # Try time, lat, lon order
                    z = var_data[:, lat_idx, lon_idx]
                except IndexError:
                    # Try other dimension orders
                    try:
                        z = var_data[lat_idx, lon_idx, :]
                    except IndexError:
                        z = var_data[lon_idx, lat_idx, :]
            else:
                raise ValueError(f"Unsupported variable dimensions: {var_data.ndim}")
                
        else:
            # Irregular grid (2D coordinates)
            # Calculate Euclidean distance to each grid point
            if lons.shape != lats.shape:
                raise ValueError("For 2D coordinates, longitude and latitude arrays must have the same shape")
                
            dist = np.sqrt((lons - lon)**2 + (lats - lat)**2)
            
            # Find the index of the closest point
            min_idx = np.unravel_index(dist.argmin(), dist.shape)
            
            
            # Extract the value
            if var_data.ndim == 2:
                z = var_data[min_idx]
            elif var_data.ndim == 3:
                # For 3D variables
                z = var_data[:, min_idx[0], min_idx[1]]
            else:
                raise ValueError(f"Unsupported variable dimensions: {var_data.ndim}")
        
        # Handle masked values
        if isinstance(z, np.ma.MaskedArray):
            if np.all(z.mask):
                return np.nan
            elif hasattr(z, 'mask') and z.mask:
                return np.nan
        

        return z
    
    def extract_area_mean(self, variable, lon, lat, buffer_size):
        """
        Extract the mean value of a variable in a square area around a point
        
        Parameters:
        -----------
        variable : str
            Name of the variable to extract
        lon : float
            Longitude of the center point
        lat : float
            Latitude of the center point
        buffer_size : int
            Buffer size (number of pixels on each side)
            buffer_size=1 means a 3x3 pixel area around the point
        
        Returns:
        --------
        float
            Mean value of the variable in the area
        """
        # Find coordinate variables
        lon_vars = ['longitude', 'lon', 'x']
        lat_vars = ['latitude', 'lat', 'y']
        
        lon_var = None
        lat_var = None
        
        for var in lon_vars:
            if var in self.dataset.variables:
                lon_var = var
                break
                
        for var in lat_vars:
            if var in self.dataset.variables:
                lat_var = var
                break
        
        if lon_var is None or lat_var is None:
            raise ValueError("Could not find longitude/latitude variables in the dataset")
        
        # Get coordinate data
        lons = self.get_variable(lon_var)
        lats = self.get_variable(lat_var)
        
        # Find the nearest indices
        if lons.ndim == 1 and lats.ndim == 1:
            # Regular grid
            lon_idx = np.abs(lons - lon).argmin()
            lat_idx = np.abs(lats - lat).argmin()
            
            # Calculate buffer limits
            min_lon_idx = max(0, lon_idx - buffer_size)
            max_lon_idx = min(len(lons) - 1, lon_idx + buffer_size)
            min_lat_idx = max(0, lat_idx - buffer_size)
            max_lat_idx = min(len(lats) - 1, lat_idx + buffer_size)
            
            # Extract the area data
            try:
                # Try lat, lon order
                area_data = self.dataset.variables[variable][min_lat_idx:max_lat_idx+1, 
                                                             min_lon_idx:max_lon_idx+1]
            except IndexError:
                # Try lon, lat order
                area_data = self.dataset.variables[variable][min_lon_idx:max_lon_idx+1, 
                                                             min_lat_idx:max_lat_idx+1]
        else:
            # Irregular grid
            # Calculate distance to each grid point
            dist = np.sqrt((lons - lon)**2 + (lats - lat)**2)
            
            # Find the index of the closest point
            center_idx = np.unravel_index(dist.argmin(), dist.shape)
            
            # Calculate buffer limits
            min_idx0 = max(0, center_idx[0] - buffer_size)
            max_idx0 = min(lons.shape[0] - 1, center_idx[0] + buffer_size)
            min_idx1 = max(0, center_idx[1] - buffer_size)
            max_idx1 = min(lons.shape[1] - 1, center_idx[1] + buffer_size)
            
            # Extract the area data
            area_data = self.dataset.variables[variable][min_idx0:max_idx0+1, 
                                                         min_idx1:max_idx1+1]
        
        # Calculate the mean, ignoring NaN values
        if isinstance(area_data, np.ma.MaskedArray):
            # For masked arrays, convert to a regular array with NaNs
            area_data = area_data.filled(np.nan)
        
        mean_value = np.nanmean(area_data)
        

        return mean_value
    
    def _find_nearest_index(self, array, value):
        """Find the index of the nearest value in an array"""
        array = np.asarray(array)
        return np.abs(array - value).argmin()

    def close(self):
        """Close the dataset"""
        self.dataset.close()
