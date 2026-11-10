import React, { useState } from "react";
import {
    Container,
    Typography,
    TextField,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    Slider,
    Switch,
    FormControlLabel,
    Radio,
    RadioGroup,
    Checkbox,
    Button,
    Box,
} from "@mui/material";

export default function ElementsPage() {
    const [formData, setFormData] = useState({
        selectValue: "",
        textInput: "",
        rangeValue: 50,
        switchValue: false,
        radioValue: "",
        checkboxValues: [],
    });

    const handleChange = (event) => {
        const { name, value, type, checked } = event.target;

        setFormData((prevState) => {
            // Specifically handle switch separately
            if (name === "switchValue") {
                return {
                    ...prevState,
                    switchValue: checked,
                };
            }

            if (type === "checkbox") {
                // Handle checkbox array
                if (checked) {
                    return {
                        ...prevState,
                        checkboxValues: [...prevState.checkboxValues, value],
                    };
                } else {
                    return {
                        ...prevState,
                        checkboxValues: prevState.checkboxValues.filter(
                            (item) => item !== value
                        ),
                    };
                }
            }

            return {
                ...prevState,
                [name]: value,
            };
        });
    };

    const handleRangeChange = (event, newValue) => {
        setFormData((prevState) => ({
            ...prevState,
            rangeValue: newValue,
        }));
    };

    const handleSubmit = (event) => {
        event.preventDefault();
        console.log("Form Data:", formData);
    };

    return (
        <Container maxWidth="sm" sx={{ mt: 5, mb: 5}}>
            <Typography variant="h4" gutterBottom>
                Material UI Form Demo
            </Typography>
            <form onSubmit={handleSubmit}>
                {/* Select Input */}
                <FormControl fullWidth margin="normal">
                    <InputLabel>Select Option</InputLabel>
                    <Select
                        name="selectValue"
                        value={formData.selectValue}
                        label="Select Option"
                        onChange={handleChange}
                    >
                        <MenuItem value="option1">Option 1</MenuItem>
                        <MenuItem value="option2">Option 2</MenuItem>
                        <MenuItem value="option3">Option 3</MenuItem>
                    </Select>
                </FormControl>

                {/* Text Input */}
                <TextField
                    fullWidth
                    margin="normal"
                    name="textInput"
                    label="Text Input"
                    value={formData.textInput}
                    onChange={handleChange}
                />

                {/* Range Slider */}
                <Box mt={3} mb={2}>
                    <Typography gutterBottom>Range Slider</Typography>
                    <Slider
                        value={formData.rangeValue}
                        onChange={handleRangeChange}
                        valueLabelDisplay="auto"
                        min={0}
                        max={100}
                    />
                </Box>

                {/* Switch */}
                <FormControlLabel
                    control={
                        <Switch
                            name="switchValue"
                            checked={formData.switchValue}
                            onChange={handleChange}
                        />
                    }
                    label="Toggle Switch"
                />

                {/* Radio Buttons */}
                <FormControl component="fieldset" fullWidth margin="normal">
                    <Typography>Radio Buttons</Typography>
                    <RadioGroup
                        name="radioValue"
                        value={formData.radioValue}
                        onChange={handleChange}
                    >
                        <FormControlLabel
                            value="radio1"
                            control={<Radio />}
                            label="Radio Option 1"
                        />
                        <FormControlLabel
                            value="radio2"
                            control={<Radio />}
                            label="Radio Option 2"
                        />
                        <FormControlLabel
                            value="radio3"
                            control={<Radio />}
                            label="Radio Option 3"
                        />
                    </RadioGroup>
                </FormControl>

                {/* Checkboxes */}
                <FormControl component="fieldset" fullWidth margin="normal">
                    <Typography>Checkboxes</Typography>
                    <FormControlLabel
                        control={
                            <Checkbox
                                name="checkboxValues"
                                value="check1"
                                checked={formData.checkboxValues.includes(
                                    "check1"
                                )}
                                onChange={handleChange}
                            />
                        }
                        label="Checkbox Option 1"
                    />
                    <FormControlLabel
                        control={
                            <Checkbox
                                name="checkboxValues"
                                value="check2"
                                checked={formData.checkboxValues.includes(
                                    "check2"
                                )}
                                onChange={handleChange}
                            />
                        }
                        label="Checkbox Option 2"
                    />
                    <FormControlLabel
                        control={
                            <Checkbox
                                name="checkboxValues"
                                value="check3"
                                checked={formData.checkboxValues.includes(
                                    "check3"
                                )}
                                onChange={handleChange}
                            />
                        }
                        label="Checkbox Option 3"
                    />
                </FormControl>

                {/* Submit Button */}
                <Box mt={3}>
                    <Button
                        type="submit"
                        variant="contained"
                        color="primary"
                        fullWidth
                    >
                        Submit
                    </Button>
                </Box>
            </form>
        </Container>
    );
}
