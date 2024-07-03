import os
import vtk
import pydicom
import json

class MouseInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self, parent=None):
        self.AddObserver("LeftButtonPressEvent", self.left_button_press_event)
        self.AddObserver("RightButtonPressEvent", self.right_button_press_event)
        self.AddObserver("MouseMoveEvent", self.mouse_move_event)
        self.AddObserver("KeyPressEvent", self.key_press_event)
        self.annotations = []
        self.dots = []
        self.text_actors = []
        self.dot_radius = 2.0
        self.selected_dot = None
        self.moving_dot = False
        self.image_bounds = None
        self.point_counter = 1  # Counter for numbering points

    def set_image_bounds(self, bounds):
        self.image_bounds = bounds

    def is_within_bounds(self, position):
        if self.image_bounds is None:
            return False
        x_min, x_max, y_min, y_max, z_min, z_max = self.image_bounds
        return (x_min <= position[0] <= x_max and
                y_min <= position[1] <= y_max and
                z_min <= position[2] <= z_max)

    def left_button_press_event(self, obj, event):
        click_pos = self.GetInteractor().GetEventPosition()
        picker = vtk.vtkPropPicker()
        picker.Pick(click_pos[0], click_pos[1], 0, self.GetDefaultRenderer())
        position = picker.GetPickPosition()

        if not self.is_within_bounds(position):
            return

        actor = picker.GetActor()

        if actor in self.dots:
            if self.selected_dot:
                self.selected_dot.GetProperty().SetColor(0, 0, 0)  # Deselect the previous dot
            self.selected_dot = actor
            self.selected_dot.GetProperty().SetColor(1, 0, 0)  # Highlight the selected dot
            self.moving_dot = True
        else:
            print(f"Clicked position: {position}")
            self.annotations.append({"id": self.point_counter, "x": position[0], "y": position[1], "z": position[2]})
            self.point_counter += 1

            # Create a black dot at the clicked position
            sphere_source = vtk.vtkSphereSource()
            sphere_source.SetCenter(position)
            sphere_source.SetRadius(self.dot_radius)

            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(sphere_source.GetOutputPort())

            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(0, 0, 0)  # Black color

            self.GetDefaultRenderer().AddActor(actor)
            self.dots.append(actor)

            # Create a text label for the dot
            text_source = vtk.vtkVectorText()
            text_source.SetText(f"{self.point_counter - 1}")

            text_mapper = vtk.vtkPolyDataMapper()
            text_mapper.SetInputConnection(text_source.GetOutputPort())

            text_actor = vtk.vtkFollower()
            text_actor.SetMapper(text_mapper)
            text_actor.SetScale(0.5, 0.5, 0.5)
            text_actor.SetPosition(position)
            text_actor.GetProperty().SetColor(1.0, 1.0, 1.0)  # White color

            self.GetDefaultRenderer().AddActor(text_actor)
            text_actor.SetCamera(self.GetDefaultRenderer().GetActiveCamera())

            self.text_actors.append(text_actor)

            self.GetInteractor().GetRenderWindow().Render()

            self.OnLeftButtonDown()
        return

    def right_button_press_event(self, obj, event):
        click_pos = self.GetInteractor().GetEventPosition()
        picker = vtk.vtkPropPicker()
        picker.Pick(click_pos[0], click_pos[1], 0, self.GetDefaultRenderer())
        position = picker.GetPickPosition()

        if not self.is_within_bounds(position):
            return

        actor = picker.GetActor()

        if actor in self.dots:
            index = self.dots.index(actor)
            self.GetDefaultRenderer().RemoveActor(actor)
            self.GetDefaultRenderer().RemoveActor(self.text_actors[index])
            self.dots.pop(index)
            self.annotations.pop(index)
            self.text_actors.pop(index)
            self.GetInteractor().GetRenderWindow().Render()
        self.OnRightButtonDown()
        return

    def mouse_move_event(self, obj, event):
        if self.moving_dot and self.selected_dot:
            click_pos = self.GetInteractor().GetEventPosition()
            picker = vtk.vtkPropPicker()
            picker.Pick(click_pos[0], click_pos[1], 0, self.GetDefaultRenderer())
            position = picker.GetPickPosition()

            if not self.is_within_bounds(position):
                return

            sphere_source = self.selected_dot.GetMapper().GetInputConnection(0, 0).GetProducer()
            sphere_source.SetCenter(position)
            self.GetInteractor().GetRenderWindow().Render()

            index = self.dots.index(self.selected_dot)
            self.annotations[index] = {"id": index + 1, "x": position[0], "y": position[1], "z": position[2]}
            self.text_actors[index].SetPosition(position)
        self.OnMouseMove()
        return

    def key_press_event(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key == "Up":
            self.dot_radius += 1.0
        elif key == "Down":
            self.dot_radius = max(1.0, self.dot_radius - 1.0)  # Ensure radius doesn't go below 1
        elif key == "Delete" and self.selected_dot:
            index = self.dots.index(self.selected_dot)
            self.GetDefaultRenderer().RemoveActor(self.selected_dot)
            self.GetDefaultRenderer().RemoveActor(self.text_actors[index])
            self.dots.pop(index)
            self.annotations.pop(index)
            self.text_actors.pop(index)
            self.selected_dot = None
            self.GetInteractor().GetRenderWindow().Render()
        self.update_dot_sizes()
        self.OnKeyPress()
        return

    def update_dot_sizes(self):
        for dot in self.dots:
            sphere_source = dot.GetMapper().GetInputConnection(0, 0).GetProducer()
            radius = self.dot_radius
            if dot == self.selected_dot:
                radius *= 1.5
            sphere_source.SetRadius(radius)
        self.GetInteractor().GetRenderWindow().Render()

    def save_annotations(self, filename):
        with open(filename, 'w') as outfile:
            json.dump(self.annotations, outfile, indent=4)

def load_dicom_folder(folder_path):
    reader = vtk.vtkDICOMImageReader()
    reader.SetDirectoryName(folder_path)
    reader.Update()
    return reader.GetOutput()

def apply_bone_threshold(volume):
    bone_extractor = vtk.vtkMarchingCubes()
    bone_extractor.SetInputData(volume)
    bone_extractor.SetValue(0, 150)  # Adjust this threshold based on your data
    bone_extractor.Update()
    return bone_extractor.GetOutput()

def extract_largest_component(poly_data):
    connectivity_filter = vtk.vtkPolyDataConnectivityFilter()
    connectivity_filter.SetInputData(poly_data)
    connectivity_filter.SetExtractionModeToLargestRegion()
    connectivity_filter.Update()
    return connectivity_filter.GetOutput()

def visualize_ct_dicom(folder_path):
    dicom_volume = load_dicom_folder(folder_path)
    bone_data = apply_bone_threshold(dicom_volume)
    largest_bone_component = extract_largest_component(bone_data)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(largest_bone_component)
    mapper.ScalarVisibilityOff()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.SetBackground(0.1, 0.2, 0.3)

    render_window = vtk.vtkRenderWindow()
    render_window.AddRenderer(renderer)

    interactor = vtk.vtkRenderWindowInteractor()
    interactor_style = MouseInteractorStyle()
    interactor.SetInteractorStyle(interactor_style)
    interactor.SetRenderWindow(render_window)

    interactor_style.SetDefaultRenderer(renderer)
    
    # Set image bounds for interactor style
    bounds = largest_bone_component.GetBounds()
    interactor_style.set_image_bounds(bounds)
    
    render_window.Render()
    interactor.Start()

    interactor_style.save_annotations("annotations.json")

if __name__ == "__main__":
    dicom_folder_path = "C:\\Users\\Asus\\Downloads\\kneect"
    visualize_ct_dicom(dicom_folder_path)
